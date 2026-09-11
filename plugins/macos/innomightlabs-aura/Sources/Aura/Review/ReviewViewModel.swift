import AVFoundation
import Combine
import CoreMedia
import Foundation

/// Drives one review window: owns the player, the resolved timeline, and the playhead.
///
/// `@MainActor` is forced rather than stylistic — `AVPlayer` and `AVPlayerItem` are
/// main-actor types.
@MainActor
final class ReviewViewModel: ObservableObject {
    enum LoadState: Equatable {
        case loading
        case ready
        case failed(String)
    }

    enum TranscriptState: Equatable {
        case absent
        case transcribing
        case ready
        case failed(String)
    }

    enum AgentState: Equatable {
        case idle
        case thinking
        case failed(String)
    }

    struct AgentTurn: Identifiable, Equatable {
        enum Speaker { case user, agent }

        let id = UUID()
        let speaker: Speaker
        let text: String
    }

    enum ExportState: Equatable {
        case idle
        case running(fraction: Double)
        case finished(URL)
        case failed(String)
    }

    @Published private(set) var state: LoadState = .loading
    /// Ticks ~30x a second while playing, so the scrubber and waveform cursor can follow it.
    @Published private(set) var playhead: CMTime = .zero
    @Published private(set) var isPlaying = false
    @Published private(set) var timeline: ResolvedTimeline?
    @Published var lastError: String?

    /// Session markers, already converted onto the media timeline.
    @Published private(set) var markers: [EventTimeline.Entry] = []
    @Published private(set) var peaks: [AudioLane: WaveformPeaks] = [:]
    @Published private(set) var transcript: Transcript?
    @Published private(set) var transcriptState: TranscriptState = .absent
    /// Published only when it changes, so the transcript list is not invalidated 30x a second.
    @Published private(set) var activeCueID: Transcript.Segment.ID?
    @Published private(set) var exportState: ExportState = .idle
    /// How much of the timeline the waveform lanes show. `nil` fits the whole recording;
    /// anything else is a window that follows the playhead, which is what makes frame-level
    /// edits possible without a separate pan control.
    @Published private(set) var visibleDuration: TimeInterval?
    @Published private(set) var agentState: AgentState = .idle
    /// Proposed edits, never applied until accepted.
    @Published private(set) var suggestions: [EditSuggestion] = []
    /// The conversation for this recording. One conversation per video, so the user can keep
    /// talking as they edit instead of restating context every time.
    @Published private(set) var conversation: [AgentTurn] = []

    let folder: SessionFolder
    /// One long-lived player for the window's whole life. Never replaced: a periodic time
    /// observer's token can only be removed from the player that produced it, and passing it
    /// to a different one raises an exception.
    let player = AVPlayer()

    @Published private(set) var store: EditDocumentStore?
    private let builder: any CompositionBuilding
    private let exporter: any ExportEngine
    private let suggester: any EditSuggesting
    private var suggestTask: Task<Void, Never>?
    private let extractor = WaveformExtractor()
    private var probes: [SourceTrackProbe] = []
    private var eventTimeline = EventTimeline(events: [])
    private var timeObserver: Any?
    private var cancellables: Set<AnyCancellable> = []
    private var endObserver: NSObjectProtocol?
    /// Separate handles: the transcript's "Try Again" used to cancel a shared task and take
    /// in-flight waveform extraction down with it, with nothing to restart it.
    private var waveformTask: Task<Void, Never>?
    private var transcriptTask: Task<Void, Never>?
    private var exportTask: Task<Void, Never>?
    /// Bumped whenever an export starts or is cancelled. A task whose generation no longer
    /// matches has been superseded and must not touch shared state — otherwise a cancelled
    /// export unwinding late overwrites the state, or clears the handle, of the one after it.
    private var exportGeneration = 0
    /// Rebuilds are serialized: undo/redo held down, or a burst of agent-applied operations,
    /// would otherwise leave two builds racing to `replaceCurrentItem` and the later document
    /// losing to the earlier one's item.
    private var rebuildTask: Task<Void, Never>?

    /// Caps the preview's render size. Compositing a Retina screen capture and a camera means
    /// two HEVC decodes per composed frame, which drops frames on lower-end machines; the
    /// export builds from the same timeline at full size.
    private static let previewMaxDimension: CGFloat = 1600

    var duration: CMTime { timeline?.duration ?? .zero }
    var document: SessionEdit? { store?.document }

    init(
        folder: SessionFolder,
        builder: any CompositionBuilding = LayerInstructionCompositionBuilder(),
        exporter: any ExportEngine = AVAssetExportEngine(),
        suggester: any EditSuggesting = InnomightLabsEditSuggester()
    ) {
        self.folder = folder
        self.builder = builder
        self.exporter = exporter
        self.suggester = suggester
    }

    // MARK: - Loading

    func load() async {
        guard case .loading = state else { return }

        probes = await SourceTrackProbe.probeAll(in: folder)
        guard !probes.isEmpty else {
            state = .failed("This session has no readable media.")
            return
        }

        // The four files share a time origin but not a duration, so the recording is as long
        // as its longest track rather than any particular one.
        let recordedDuration = probes.map(\.duration).max() ?? .zero
        let micOffset = probes.first { $0.kind == .microphone }?.leadingEmptyEdit ?? .zero

        let store = EditDocumentStore.load(
            folder: folder,
            duration: Timeline.seconds(recordedDuration),
            micTimeOffset: Timeline.seconds(micOffset)
        )
        self.store = store

        // Rebuild whenever the document changes, from whatever source — a drag, an agent
        // suggestion, or an undo.
        store.$document
            .dropFirst()
            .removeDuplicates()
            .sink { [weak self] document in
                self?.scheduleRebuild(document: document)
            }
            .store(in: &cancellables)

        eventTimeline = EventTimeline.load(eventsURL: folder.eventsURL)
        markers = eventTimeline.markers

        await rebuild(document: store.document, preservingPlayhead: false)
        startObservingTime()

        // Waveforms and the transcript are loaded after the window is already playable —
        // neither is needed to start watching, and a cold transcription takes a while.
        // Concurrently, because they are independent: making the transcript wait on a
        // multi-second waveform decode would delay the panel for no reason.
        waveformTask = Task { [weak self] in await self?.loadWaveforms() }
        transcriptTask = Task { [weak self] in await self?.loadTranscript() }
    }

    private func loadWaveforms() async {
        let lanes: [(AudioLane, URL, URL)] = [
            (.microphone, folder.microphoneURL, folder.microphonePeaksURL),
            (.systemAudio, folder.systemAudioURL, folder.systemAudioPeaksURL)
        ]

        for (lane, url, cacheURL) in lanes {
            guard let probe = probes.first(where: { $0.kind.lane == lane }) else { continue }
            let extracted = await extractor.peaks(for: url, cacheURL: cacheURL, duration: probe.duration)
            guard !Task.isCancelled else { return }
            peaks[lane] = extracted
        }
    }

    private func scheduleRebuild(document: SessionEdit) {
        let previous = rebuildTask
        rebuildTask = Task { @MainActor [weak self] in
            _ = await previous?.value
            guard !Task.isCancelled else { return }
            await self?.rebuild(document: document, preservingPlayhead: true)
        }
    }

    private func rebuild(document: SessionEdit, preservingPlayhead: Bool) async {
        let resolved = TimelineResolver.resolve(document: document, probes: probes)
        let wasReady = state == .ready

        do {
            let built = try await builder.build(resolved, maxRenderDimension: Self.previewMaxDimension)
            let resumeAt = preservingPlayhead ? player.currentTime() : .zero
            let wasPlaying = isPlaying

            let item = AVPlayerItem(asset: built.asset)
            item.videoComposition = built.videoComposition
            item.audioMix = built.audioMix
            // With a video composition in play, this makes `currentTime` report the frame
            // actually on screen instead of running ahead of the compositor. It is the knob
            // that makes the transcript and waveform line up with what the user sees.
            item.seekingWaitsForVideoCompositionRendering = true

            player.replaceCurrentItem(with: item)
            observeEnd(of: item)

            timeline = resolved
            state = .ready

            if resumeAt > .zero, resumeAt < built.duration {
                await seek(to: resumeAt, exact: true)
                if wasPlaying { play() }
            } else {
                playhead = .zero
            }
        } catch {
            // Only a failure to open at all is fatal. Once the window is up, an edit that
            // can't be built (clips outside every recorded file, a source file moved away)
            // has to leave the last good composition playing and stay interactive — the
            // error screen hides the very undo button needed to back the edit out.
            if wasReady {
                lastError = error.localizedDescription
            } else {
                state = .failed(error.localizedDescription)
            }
        }
    }

    // MARK: - Playhead

    private func startObservingTime() {
        guard timeObserver == nil else { return }

        // Matching the composition's frame duration: observing faster than the compositor
        // renders buys nothing. Views that want smoother motion interpolate locally.
        timeObserver = player.addPeriodicTimeObserver(
            forInterval: Timeline.frameDuration,
            queue: .main
        ) { [weak self] time in
            // `assumeIsolated` rather than `Task { @MainActor in }`: the latter would spawn
            // 30 tasks a second and, worse, reorder against seeks, making the playhead jump
            // backwards after a scrub. Safe only because the observer is on the main queue.
            MainActor.assumeIsolated {
                self?.handleTick(time)
            }
        }
    }

    private func handleTick(_ time: CMTime) {
        playhead = time

        // Gate the transcript's invalidation on the highlighted cue actually changing.
        let cue = transcript?.segment(at: transcriptTime(forComposition: time))?.id
        if cue != activeCueID {
            activeCueID = cue
        }
    }

    private func observeEnd(of item: AVPlayerItem) {
        if let endObserver {
            NotificationCenter.default.removeObserver(endObserver)
        }
        // A periodic observer never fires a final tick exactly at the duration, so the
        // playhead would otherwise settle a frame short.
        endObserver = NotificationCenter.default.addObserver(
            forName: AVPlayerItem.didPlayToEndTimeNotification,
            object: item,
            queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                self.isPlaying = false
                self.playhead = self.duration
            }
        }
    }

    /// Must be called before the window goes away. Teardown cannot live in `deinit`:
    /// `AVPlayer` is main-actor isolated and `deinit` is not, so touching it there would not
    /// compile — and dropping a time observer without removing it is undefined behaviour.
    func close() {
        if let timeObserver {
            player.removeTimeObserver(timeObserver)
        }
        timeObserver = nil
        if let endObserver {
            NotificationCenter.default.removeObserver(endObserver)
        }
        endObserver = nil
        player.pause()
        waveformTask?.cancel()
        transcriptTask?.cancel()
        exportTask?.cancel()
        rebuildTask?.cancel()
        suggestTask?.cancel()
        cancellables.removeAll()
        store?.flush()
    }

    // MARK: - Transport

    func play() {
        guard case .ready = state else { return }
        player.play()
        isPlaying = true
    }

    func pause() {
        player.pause()
        isPlaying = false
    }

    func togglePlayback() {
        isPlaying ? pause() : play()
    }

    /// Coarse seeks while scrubbing keep the compositor responsive; the exact one lands on
    /// release. Exact seeks at drag rate through a composition stutter badly.
    func seek(to time: CMTime, exact: Bool) async {
        guard case .ready = state else { return }
        let clamped = min(max(.zero, Timeline.normalized(time)), duration)
        playhead = clamped

        let tolerance = exact ? CMTime.zero : CMTime(value: 1, timescale: 10)
        await player.seek(to: clamped, toleranceBefore: tolerance, toleranceAfter: tolerance)
    }

    func scrub(to seconds: TimeInterval) {
        Task { await seek(to: Timeline.time(seconds: seconds), exact: false) }
    }

    func commitScrub(to seconds: TimeInterval) {
        Task { await seek(to: Timeline.time(seconds: seconds), exact: true) }
    }

    // MARK: - Zoom

    /// Below this the peak buckets (1/100s) start showing as steps rather than a waveform.
    private static let minimumVisibleDuration: TimeInterval = 0.25
    private static let zoomFactor: TimeInterval = 1.8

    /// The window the lanes draw, in composition time.
    var visibleSpan: TimeSpan {
        WaveformWindow.span(
            total: Timeline.seconds(duration),
            visibleDuration: visibleDuration,
            playhead: Timeline.seconds(playhead)
        )
    }

    var canZoomIn: Bool {
        (visibleDuration ?? Timeline.seconds(duration)) > Self.minimumVisibleDuration
    }

    var canZoomOut: Bool { visibleDuration != nil }

    func zoomIn() {
        let total = Timeline.seconds(duration)
        guard total > 0 else { return }
        let current = visibleDuration ?? total
        let proposed = max(Self.minimumVisibleDuration, current / Self.zoomFactor)
        visibleDuration = proposed < total ? proposed : nil
    }

    func zoomOut() {
        let total = Timeline.seconds(duration)
        guard let current = visibleDuration, total > 0 else { return }
        let proposed = current * Self.zoomFactor
        visibleDuration = proposed >= total ? nil : proposed
    }

    /// Used by pinch, where the scale arrives as a continuous multiplier.
    func setZoom(scale: Double) {
        let total = Timeline.seconds(duration)
        guard total > 0, scale > 0 else { return }
        let current = visibleDuration ?? total
        let proposed = current / scale
        visibleDuration = proposed >= total
            ? nil
            : max(Self.minimumVisibleDuration, proposed)
    }

    func zoomToFit() {
        visibleDuration = nil
    }

    // MARK: - Editing

    /// The single entry point for edits, so a drag, an agent suggestion, and a voice command
    /// all take the same path.
    @discardableResult
    func apply(_ operation: EditOperation) -> Bool {
        guard let store else { return false }
        guard store.apply(operation) else {
            lastError = store.lastError?.localizedDescription
            return false
        }
        return true
    }

    /// Converts the playhead into the session time that `EditOperation`s are expressed in.
    /// Falls back to the end of the timeline so an edit at the very last frame still lands.
    var playheadSourceTime: TimeInterval {
        guard let timeline else { return 0 }
        if let mapped = timeline.timeMap.sourceTime(forComposition: playhead) {
            return Timeline.seconds(mapped.source)
        }
        return timeline.timeMap.segments.last.map { Timeline.seconds($0.source.end) } ?? 0
    }

    var currentOverlay: OverlayKeyframe? {
        store?.document.overlay(at: playheadSourceTime)
    }

    /// Writes a keyframe at the playhead, which is what makes an overlay change take effect
    /// from that moment on rather than retroactively for the whole recording.
    func setOverlay(rect: NormalizedRect, visible: Bool) {
        apply(.setOverlayKeyframe(OverlayKeyframe(t: playheadSourceTime, rect: rect, visible: visible)))
    }

    func toggleOverlayVisibility() {
        guard let current = currentOverlay else { return }
        setOverlay(rect: current.rect, visible: !current.visible)
    }

    func setLaneMuted(_ lane: AudioLane, _ muted: Bool) {
        apply(.setLaneMuted(lane: lane, muted: muted))
    }

    func setLaneGain(_ lane: AudioLane, _ gain: Double) {
        apply(.setLaneGain(lane: lane, keyframe: GainKeyframe(t: playheadSourceTime, gain: gain)))
    }

    // MARK: - A/V slip

    /// The correction already applied automatically from the recorded track start offsets,
    /// shown so the user can tell "already handled" from "needs a nudge".
    func automaticCorrection(for lane: AudioLane) -> TimeInterval {
        guard let probe = timeline?.audio.first(where: { $0.lane == lane })?.probe else { return 0 }
        return Timeline.seconds(probe.alignmentCorrection)
    }

    func laneOffset(_ lane: AudioLane) -> TimeInterval {
        store?.document.offset(for: lane) ?? 0
    }

    func nudgeLaneOffset(_ lane: AudioLane, by delta: TimeInterval) {
        let proposed = ((laneOffset(lane) + delta) * 1000).rounded() / 1000
        guard abs(proposed) <= SessionEdit.maximumLaneOffset else { return }
        apply(.setLaneOffset(lane: lane, seconds: proposed))
    }

    func resetLaneOffset(_ lane: AudioLane) {
        apply(.setLaneOffset(lane: lane, seconds: 0))
    }

    // MARK: - Transcript

    /// Composition time -> the clock the transcript is stamped in.
    private func transcriptTime(forComposition time: CMTime) -> TimeInterval {
        guard
            let timeline,
            let mapped = timeline.timeMap.sourceTime(forComposition: time)
        else { return 0 }
        return Timeline.seconds(mapped.source) - (store?.document.micTimeOffset ?? 0)
    }

    /// Where a transcript cue appears on the composition timeline. Empty when the cue's
    /// content was cut, and more than one entry if a cut split it.
    func compositionSpans(for segment: Transcript.Segment) -> [TimeSpan] {
        guard let timeline else { return [] }
        let offset = store?.document.micTimeOffset ?? 0
        return timeline.timeMap.compositionSpans(
            forSource: TimeSpan(start: segment.start + offset, end: segment.end + offset)
        )
    }

    func seek(to segment: Transcript.Segment) {
        guard let start = compositionSpans(for: segment).first?.start else { return }
        Task { await seek(to: Timeline.time(seconds: start), exact: true) }
    }

    /// Removes the range a transcript cue occupies. The operation is expressed in session
    /// time, so it stays correct regardless of what has already been cut.
    func removeRange(of segment: Transcript.Segment) {
        let offset = store?.document.micTimeOffset ?? 0
        apply(.removeRange(TimeSpan(start: segment.start + offset, end: segment.end + offset)))
    }

    private func loadTranscript() async {
        if let existing = Transcript.load(from: folder.transcriptURL) {
            transcript = existing
            transcriptState = .ready
            return
        }

        guard probes.contains(where: { $0.kind == .microphone }) else { return }
        transcriptState = .transcribing

        do {
            let produced = try await SessionTranscriber().transcribe(microphoneURL: folder.microphoneURL)
            guard !Task.isCancelled else { return }
            produced.write(to: folder.transcriptURL)
            transcript = produced
            transcriptState = .ready
        } catch {
            guard !Task.isCancelled else { return }
            transcriptState = .failed(error.localizedDescription)
        }
    }

    func retryTranscription() {
        guard transcriptState != .transcribing else { return }
        transcriptTask?.cancel()
        transcriptTask = Task { [weak self] in await self?.loadTranscript() }
    }

    // MARK: - Agent

    var isAgentConfigured: Bool { AgentSettings.isConfigured }

    /// The compact description the agent reasons from, rebuilt at request time so it reflects
    /// the edit as it currently stands, and written to `digest.json` so what the agent was
    /// told is always inspectable.
    @discardableResult
    func buildDigest() -> SessionDigest? {
        guard let document = store?.document else { return nil }

        let digest = SessionDigest.make(
            sessionID: folder.id,
            duration: Timeline.seconds(duration),
            probes: probes,
            events: eventTimeline,
            document: document,
            transcript: transcript
        )
        digest.write(to: folder.digestURL)
        return digest
    }

    /// Asks the agent what to change. Nothing is applied here — suggestions are staged for
    /// the user to accept, and accepting routes through the same `apply` a drag does.
    func requestSuggestions(instruction: String) {
        guard let document = store?.document, suggestTask == nil else { return }

        let context = EditSuggestionContext(
            sessionID: folder.id,
            duration: Timeline.seconds(duration),
            transcript: transcript,
            document: document,
            markers: markers.map { (time: $0.mediaTs, label: $0.event.label ?? "Marker") },
            digest: buildDigest()
        )

        conversation.append(AgentTurn(speaker: .user, text: instruction))
        agentState = .thinking
        suggestTask = Task { [weak self] in
            guard let self else { return }
            defer { self.suggestTask = nil }

            do {
                let result = try await self.suggester.suggest(instruction: instruction, context: context)
                guard !Task.isCancelled else { return }
                if !result.reply.isEmpty {
                    self.conversation.append(AgentTurn(speaker: .agent, text: result.reply))
                }
                // Replaces rather than accumulates: a new answer supersedes the previous
                // proposal, and leaving stale operations pending invites applying edits the
                // user has already moved past.
                self.suggestions = result.suggestions
                self.agentState = .idle
            } catch {
                guard !Task.isCancelled else { return }
                self.agentState = .failed(error.localizedDescription)
            }
        }
    }

    var isAwaitingAgent: Bool { agentState == .thinking }

    func accept(_ suggestion: EditSuggestion) {
        guard apply(suggestion.operation) else { return }
        suggestions.removeAll { $0.id == suggestion.id }
    }

    func acceptAllSuggestions() {
        guard let store else { return }
        let operations = suggestions.map(\.operation)
        guard !operations.isEmpty else { return }

        // All-or-nothing, and one undo step: a half-applied set of suggestions is worse
        // than none.
        if store.apply(operations) {
            suggestions = []
        } else {
            lastError = store.lastError?.localizedDescription
        }
    }

    func reject(_ suggestion: EditSuggestion) {
        suggestions.removeAll { $0.id == suggestion.id }
    }

    func dismissSuggestions() {
        suggestions = []
    }

    /// Clears the visible transcript of the chat. The server-side conversation is untouched —
    /// the agent still remembers, which is the point of one conversation per recording.
    func clearConversationView() {
        conversation = []
        suggestions = []
        agentState = .idle
    }

    // MARK: - Export

    /// Where an export defaults to: beside the recording, named after the session.
    var suggestedExportURL: URL {
        folder.rootURL.appendingPathComponent("\(folder.id).mp4")
    }

    /// Exports at full render size from the same timeline the preview uses, so the file
    /// matches what was previewed rather than coming from a second code path.
    func export(to destination: URL) {
        guard let timeline, exportTask == nil else { return }

        exportGeneration += 1
        let generation = exportGeneration
        exportState = .running(fraction: 0)

        exportTask = Task { [weak self] in
            guard let self else { return }

            do {
                let built = try await self.builder.build(timeline, maxRenderDimension: nil)
                try await self.exporter.export(built, to: destination) { progress in
                    switch progress {
                    case .preparing:
                        self.report(.running(fraction: 0), generation: generation)
                    case .exporting(let fraction):
                        self.report(.running(fraction: fraction), generation: generation)
                    }
                }
                self.report(.finished(destination), generation: generation)
            } catch {
                // AVFoundation reports cancellation as `AVError.operationCancelled`, not
                // `CancellationError`, so matching only the latter would flip the button to
                // "Export Failed" right after the user pressed Cancel.
                if Task.isCancelled || (error as? AVError)?.code == .operationCancelled {
                    self.report(.idle, generation: generation)
                } else {
                    self.report(.failed(error.localizedDescription), generation: generation)
                }
            }

            if generation == self.exportGeneration {
                self.exportTask = nil
            }
        }
    }

    private func report(_ state: ExportState, generation: Int) {
        guard generation == exportGeneration else { return }
        exportState = state
    }

    func cancelExport() {
        exportGeneration += 1
        exportTask?.cancel()
        exportTask = nil
        exportState = .idle
    }
}
