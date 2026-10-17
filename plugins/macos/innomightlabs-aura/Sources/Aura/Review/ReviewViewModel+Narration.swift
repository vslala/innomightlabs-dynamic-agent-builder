import Foundation

extension ReviewViewModel {
    /// Speaks a line of narration and, only once its clip exists, puts it in the document, so the
    /// document never describes audio that is not there. Like `replaceSpeech`, this is how an
    /// agent's rewrite becomes real: the suggestion is a draft until it has been spoken.
    ///
    /// The clip is written beside the live one and moved into place after the edit is accepted, so
    /// a rejected rewrite cannot destroy the line it was meant to replace.
    func speakNarration(_ draft: NarrationLine, suggestionID: UUID? = nil) {
        Task { [weak self] in
            guard let self else { return }
            do {
                let voice = try NarrationVoice.resolve()
                let spoken = try await SpeechReplacementRenderer.speakNaturally(
                    text: draft.text, voice: NarrationVoice.reference, using: voice.synthesizer
                )
                let pending = folder.narrationURL.appendingPathComponent("\(draft.id.uuidString)-new.m4a")
                let duration = try SpeechReplacementRenderer.write(spoken, to: pending)
                defer { try? FileManager.default.removeItem(at: pending) }

                var line = draft
                line.duration = duration
                guard apply(.setNarration(line)) else { return }

                let live = folder.narrationClipURL(for: line.id)
                try? FileManager.default.removeItem(at: live)
                try FileManager.default.copyItem(at: pending, to: live)
                if let suggestionID { dismissSuggestion(id: suggestionID) }
                lastNotice = "Narration updated."
            } catch is CancellationError {
                return
            } catch {
                lastError = error.localizedDescription
            }
        }
    }
}
