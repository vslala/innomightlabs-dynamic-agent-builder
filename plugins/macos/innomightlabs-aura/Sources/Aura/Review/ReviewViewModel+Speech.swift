import Foundation

/// One selection to be re-spoken.
struct SpeechRequest: Equatable, Identifiable, Sendable {
    /// Becomes the replacement's id, so a selection re-spoken again swaps the old one.
    let id: UUID
    let span: TimeSpan
    let text: String
    let originalText: String
    /// The agent suggestion this came from, which leaves the list once it lands.
    var suggestionID: UUID? = nil
}

/// A decision the user has to make before speaking goes on.
enum PendingSpeech: Identifiable, Equatable {
    case cameraWarning(SpeechRequest)
    case longHold(SpeechRequest, seconds: Double)

    var id: String {
        switch self {
        case .cameraWarning(let request): return "camera-\(request.id)"
        case .longHold(let request, _): return "hold-\(request.id)"
        }
    }
}

enum SpeechPreparationError: Error, LocalizedError {
    case noTranscript
    case noUsableVoice

    var errorDescription: String? {
        switch self {
        case .noTranscript:
            return "Aura needs the transcript to find a clear stretch of your voice. It is still being made."
        case .noUsableVoice:
            return "Aura could not find a clear 6–10 second stretch of your voice to learn from."
        }
    }
}

extension ReviewViewModel {
    var isSpeaking: Bool { speakingFraction != nil }

    // MARK: - Starting

    /// Re-speaks `span` as `text`, in the user's voice, and puts it where the old speech was.
    func replaceSpeech(span: TimeSpan, text: String, originalText: String, id: UUID = UUID(), suggestionID: UUID? = nil) {
        enqueueSpeech([SpeechRequest(id: id, span: span, text: text, originalText: originalText, suggestionID: suggestionID)])
    }

    func enqueueSpeech(_ requests: [SpeechRequest]) {
        guard !requests.isEmpty else { return }
        guard speech.isReady else {
            lastNotice = "Turn on Speech Replacement to hear new text in your voice."
            speechSetupRequested = true
            return
        }

        speechQueue += requests
        if let document = store?.document,
           hasCamera,
           !SpeechPreferences.suppressesCameraWarning,
           let affected = requests.first(where: { document.cameraIsVisible(during: $0.span) }) {
            pendingSpeech = .cameraWarning(affected)
            return
        }
        processSpeechQueue()
    }

    /// The user went ahead despite the warning. `rememberChoice` is the "don't warn me again" box.
    func confirmCameraWarning(rememberChoice: Bool) {
        if rememberChoice { SpeechPreferences.suppressesCameraWarning = true }
        pendingSpeech = nil
        processSpeechQueue()
    }

    func acceptLongHold() {
        guard case .longHold(let request, _) = pendingSpeech, let spoken = heldSpeech else { return }
        pendingSpeech = nil
        heldSpeech = nil
        do {
            try commitSpeech(spoken, for: request)
        } catch {
            lastError = error.localizedDescription
        }
        processSpeechQueue()
    }

    /// Drops what was waiting on the user's decision, and carries on with anything queued behind it.
    func declinePendingSpeech() {
        if case .cameraWarning = pendingSpeech {
            speechQueue.removeAll()
        }
        pendingSpeech = nil
        heldSpeech = nil
        processSpeechQueue()
    }

    func cancelSpeaking() {
        speechQueue.removeAll()
        speechTask?.cancel()
    }

    // MARK: - Working through the queue

    private var hasCamera: Bool { probes.contains { $0.kind == .camera } }

    private func processSpeechQueue() {
        guard speechTask == nil, pendingSpeech == nil, !speechQueue.isEmpty else { return }

        speechTask = Task { [weak self] in
            while let self, self.pendingSpeech == nil, !self.speechQueue.isEmpty {
                let request = self.speechQueue.removeFirst()
                do {
                    try await self.speak(request)
                } catch is CancellationError {
                    self.speechQueue.removeAll()
                } catch {
                    self.speechQueue.removeAll()
                    self.lastError = error.localizedDescription
                }
            }
            self?.speakingFraction = nil
            self?.speechTask = nil
        }
    }

    private func speak(_ request: SpeechRequest) async throws {
        speakingFraction = 0
        let voice = try await prepareVoice(for: request)
        let synthesizer = try speech.synthesizer()

        let spoken = try await SpeechReplacementRenderer.speak(
            text: request.text,
            selection: request.span.duration,
            voice: voice,
            using: synthesizer
        ) { [weak self] fraction in
            Task { @MainActor in self?.speakingFraction = fraction }
        }

        if spoken.fit.needsConfirmation {
            heldSpeech = spoken
            pendingSpeech = .longHold(request, seconds: spoken.fit.hold)
            return
        }
        try commitSpeech(spoken, for: request)
    }

    /// Writes the clip and, only then, puts the edit in the document — so the document never
    /// describes speech that does not exist.
    func commitSpeech(_ spoken: SpokenText, for request: SpeechRequest) throws {
        let clipURL = folder.speechClipURL(for: request.id)
        let duration = try SpeechReplacementRenderer.write(spoken, to: clipURL)

        let applied = apply(.replaceSpeech(SpeechReplacement(
            id: request.id, span: request.span, text: request.text,
            originalText: request.originalText, duration: duration
        )))
        guard applied else {
            try? FileManager.default.removeItem(at: clipURL)
            return
        }

        if let suggestionID = request.suggestionID { dismissSuggestion(id: suggestionID) }
        switch spoken.fit.action {
        case .hold:
            lastNotice = String(format: "Replaced in your voice. The picture holds for %.1fs while the new speech finishes.", spoken.fit.hold)
        case .stretch, .pad:
            lastNotice = "Replaced in your voice."
        }
    }

    // MARK: - The voice to learn from

    /// Finds a clear stretch of the user's own speech and cuts it out for the model.
    private func prepareVoice(for request: SpeechRequest) async throws -> VoiceSample {
        guard let transcript, let microphone = probes.first(where: { $0.kind == .microphone }),
              let document = store?.document
        else { throw SpeechPreparationError.noTranscript }

        // The transcript's clock is the microphone file's; everything stored is session time.
        let offset = transcriptOffset
        let unusable = (document.cuts.map(\.span) + document.speechReplacements.map(\.span) + [request.span])
            .map { TimeSpan(start: $0.start - offset, end: $0.end - offset) }

        guard let reference = VoiceReferencePicker.pick(words: transcript.allWords, avoiding: unusable) else {
            throw SpeechPreparationError.noUsableVoice
        }

        // The cleaned copy when Studio Sound is on, since the model copies the noise it hears.
        let source = microphone.playing(studioSound: document.settings(for: .microphone).studioSound).url
        let destination = folder.voiceSampleURL
        return try await Task.detached {
            try VoiceSampleExtractor.extract(reference, from: source, to: destination)
        }.value
    }

    // MARK: - Editing the transcript

    /// What the transcript says inside `span`, for remembering what a replacement replaced.
    func spokenText(in span: TimeSpan) -> String {
        guard let transcript else { return "" }
        let offset = transcriptOffset
        return transcript.allWords
            .filter { word in
                let middle = (word.start + word.end) / 2 + offset
                return middle >= span.start && middle < span.end
            }
            .map { $0.text.trimmingCharacters(in: .whitespaces) }
            .joined(separator: " ")
    }

    func beginEditing(cue: ProjectedCue) {
        editingCueID = cue.id
    }

    func cancelEditing() {
        editingCueID = nil
    }

    /// The user changed the words of a cue: speak the new ones in its place.
    func commitEdit(of cue: ProjectedCue, to text: String) {
        editingCueID = nil
        guard let document = store?.document else { return }
        guard let changed = TranscriptDiff.changedText(from: cue.text, to: text) else {
            lastNotice = "Nothing changed, so your recording was left as it is."
            return
        }

        let existing = cue.replacementID.flatMap { id in document.speechReplacements.first { $0.id == id } }
        if let existing {
            replaceSpeech(span: existing.span, text: changed, originalText: existing.originalText, id: existing.id)
            return
        }

        guard let segment = transcript?.segments.first(where: { $0.id == cue.id }),
              let span = TranscriptDiff.span(of: segment, micOffset: transcriptOffset)
        else {
            lastError = "That line has no words to replace."
            return
        }
        replaceSpeech(span: span, text: changed, originalText: cue.text)
    }

    /// Brings the original voice back for a replaced line.
    func restoreOriginalVoice(of cue: ProjectedCue) {
        guard let id = cue.replacementID else { return }
        apply(.restoreSpeech(ids: [id]))
    }

    // MARK: - Clips

    /// The clips that exist on disk, which is all the resolver may play.
    func availableSpeechClips(for document: SessionEdit) -> [UUID: URL] {
        var clips: [UUID: URL] = [:]
        for replacement in document.speechReplacements {
            let url = folder.speechClipURL(for: replacement.id)
            if FileManager.default.fileExists(atPath: url.path) { clips[replacement.id] = url }
        }
        return clips
    }

    /// Speaks again any replacement whose clip has gone missing (a copied session, a cleared
    /// cache), from the text stored in the document, then rebuilds with it.
    ///
    /// Not part of `rebuild` itself: speaking takes seconds, and the composition should appear
    /// at once with the original voice rather than waiting on a model.
    func repairMissingSpeechClips(for document: SessionEdit, available: [UUID: URL]) {
        let missing = document.speechReplacements.filter {
            available[$0.id] == nil && !speechRepairsAttempted.contains($0.id)
        }
        guard !missing.isEmpty, speech.isReady, speechTask == nil, transcript != nil else { return }

        speechRepairsAttempted.formUnion(missing.map(\.id))
        speechTask = Task { [weak self] in
            guard let self else { return }
            for replacement in missing {
                do {
                    let request = SpeechRequest(
                        id: replacement.id, span: replacement.span,
                        text: replacement.text, originalText: replacement.originalText
                    )
                    let voice = try await self.prepareVoice(for: request)
                    let spoken = try await SpeechReplacementRenderer.speak(
                        text: replacement.text, selection: replacement.span.duration,
                        voice: voice, using: try self.speech.synthesizer()
                    )
                    try SpeechReplacementRenderer.write(spoken, to: self.folder.speechClipURL(for: replacement.id))
                } catch {
                    self.lastError = "Could not bring back the new speech at \(TimeFormatting.timecode(replacement.span.start)): "
                        + error.localizedDescription
                }
            }
            self.speechTask = nil
            if let document = self.store?.document { self.scheduleRebuildForSpeech(document: document) }
        }
    }
}
