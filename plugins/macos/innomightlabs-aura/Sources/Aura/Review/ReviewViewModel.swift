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
    /// Everything the surfaces read, with every clock already reconciled. Published at the
    /// same instant as `timeline`, never from the document sink — publishing earlier would
    /// leave a window where the waveform shows new cuts while the player is still on the old
    /// composition, which is the bug class this exists to remove.
    @Published private(set) var projection: ReviewProjection = .empty
    /// Transient: a source-time range the user has selected. Deliberately not in the
    /// document — it must not persist, must not be undoable, and must not rebuild the
    /// composition.
    @Published var selection: StampSpan<Source>?
    /// The cut region the user has selected, if any. Single click selects; double click
    /// restores, so a scrub cannot accidentally un-cut a long range.
    @Published var selectedCutRegionID: UUID?
    /// Highlighted word, published only when it changes.
    @Published private(set) var activeWordID: Int?
    @Published var lastError: String?
    /// Something the user should know that is not a failure. Separate from `lastError`
    /// because that renders a red banner, and a benign, expected event presented as an error
    /// reads as breakage.
    @Published var lastNotice: String?

    /// Session markers, already converted onto the media timeline.
    @Published private(set) var markers: [EventTimeline.Entry] = []
    @Published private(set) var peaks: [AudioLane: WaveformPeaks] = [:]
    /// High-resolution peaks for the zoomed window, keyed by lane. Nil entries mean the
    /// cached envelope is good enough at this zoom level.
    @Published private(set) var laneDetail: [AudioLane: WaveformPeaks] = [:]
    /// The window `laneDetail` describes, so a view can tell whether it is still current.
    /// The source-time window `laneDetail` covers.
    @Published private(set) var laneDetailSpan: StampSpan<Source>?
    /// Vertical axis for the lanes. Decibel by default — see `WaveformScale`.
    @Published private(set) var waveformScale: WaveformScale = ReviewPreferences.waveformScale
    @Published private(set) var transcript: Transcript?
    @Published private(set) var transcriptState: TranscriptState = .absent
    /// Published only when it changes, so the transcript list is not invalidated 30x a second.
    @Published private(set) var activeCueID: Transcript.Segment.ID?
    @Published private(set) var exportState: ExportState = .idle
    /// How much of the timeline the waveform lanes show. `nil` fits the whole recording;
    /// anything else is a window that follows the playhead, which is what makes frame-level
    /// edits possible without a separate pan control.
    @Published private(set) var visibleDuration: TimeInterval?
    /// Left edge of the zoom window, in source time. Anchored rather than following the
    /// playhead — see `visibleSpan`.
    @Published private(set) var viewportStart: TimeInterval = 0
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
    /// The document the current composition was built from, so an annotation-only change can
    /// be told from one that alters the timeline.
    private var lastBuiltDocument: SessionEdit?
    private var detailTask: Task<Void, Never>?

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
        // The *correction applied to the mic lane*, not its leading empty edit. For audio the
        // empty edit is always zero — `AVAssetWriter` discards it — so using it here left the
        // transcript on a different clock than the audio it describes.
        let micOffset = probes.first { $0.kind == .microphone }?.alignmentCorrection ?? .zero

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
                guard let self else { return }
                if let previous = self.lastBuiltDocument,
                   self.onlyAffectsAnnotations(previous, document) {
                    self.lastBuiltDocument = document
                    self.reproject()
                    return
                }
                self.scheduleRebuild(document: document)
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

    /// True when a document change cannot alter what plays, so the composition need not be
    /// rebuilt — markers and splits. Saves a player-item swap and a re-seek for an edit the
    /// timeline is indifferent to.
    private func onlyAffectsAnnotations(_ before: SessionEdit, _ after: SessionEdit) -> Bool {
        var normalised = after
        normalised.markers = before.markers
        normalised.splitPoints = before.splitPoints
        return normalised == before
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
            lastBuiltDocument = document
            projection = ReviewProjector.project(
                timeline: resolved,
                document: document,
                transcript: transcript,
                events: eventTimeline
            )
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

    /// Recomputes the projection without rebuilding the composition.
    ///
    /// Only for inputs that do not change what plays — the transcript arriving, or markers
    /// moving. Anything that alters the timeline goes through `rebuild`, so the projection and
    /// the player item always change together.
    private func reproject() {
        guard let timeline, let document = store?.document else { return }
        projection = ReviewProjector.project(
            timeline: timeline,
            document: document,
            transcript: transcript,
            events: eventTimeline
        )
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

        // Gated on the highlight actually changing, so the transcript list is not invalidated
        // 30 times a second. Resolved from the projection rather than by converting clocks
        // here.
        let word = projection.word(atComposition: Stamp(time))
        if word?.id != activeWordID {
            activeWordID = word?.id
        }
        if word?.cueID != activeCueID {
            activeCueID = word?.cueID
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
        detailTask?.cancel()
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

    /// The window the lanes draw, in **source** time — the lane shows the whole recording so
    /// cuts are visible, which means the axis is the recording's, not the edited timeline's.
    ///
    /// Anchored where the user put it rather than centred on the playhead. On a to-scale
    /// source axis the playhead teleports over every cut — 113 times on a real document — and
    /// a playhead-following window would pan the waveform each time, re-reading the audio for
    /// detail on every pan. The playhead can therefore scroll out of view while playing, which
    /// is the accepted trade for a stable view and no read thrash.
    var visibleSpan: StampSpan<Source> {
        let total = recordingDuration
        guard let visibleDuration, visibleDuration < total else {
            return StampSpan(start: 0, end: total)
        }
        let start = min(max(0, viewportStart), max(0, total - visibleDuration))
        return StampSpan(start: start, end: start + visibleDuration)
    }

    /// The recording's full extent — the zoom axis. Read from the document rather than the
    /// composition: zooming out to the composition's length would make the cut portions of the
    /// recording unreachable.
    var recordingDuration: TimeInterval {
        store?.document.recordingDuration ?? Timeline.seconds(duration)
    }

    var canZoomIn: Bool {
        (visibleDuration ?? recordingDuration) > Self.minimumVisibleDuration
    }

    var canZoomOut: Bool { visibleDuration != nil }

    func zoomIn() {
        let total = recordingDuration
        guard total > 0 else { return }
        let current = visibleDuration ?? total
        let proposed = max(Self.minimumVisibleDuration, current / Self.zoomFactor)
        zoom(to: proposed < total ? proposed : nil, around: anchor)
    }

    func zoomOut() {
        let total = recordingDuration
        guard let current = visibleDuration, total > 0 else { return }
        zoom(to: current * Self.zoomFactor >= total ? nil : current * Self.zoomFactor, around: anchor)
    }

    /// Used by pinch, where the scale arrives as a continuous multiplier.
    func setZoom(scale: Double) {
        let total = recordingDuration
        guard total > 0, scale > 0 else { return }
        let current = visibleDuration ?? total
        let proposed = current / scale
        zoom(
            to: proposed >= total ? nil : max(Self.minimumVisibleDuration, proposed),
            around: anchor
        )
    }

    func setWaveformScale(_ scale: WaveformScale) {
        waveformScale = scale
        ReviewPreferences.waveformScale = scale
    }

    /// Where zooming keeps its focus: the playhead if it is on screen, otherwise the middle
    /// of the current window — so zooming never jumps the user somewhere they weren't looking.
    private var anchor: Stamp<Source> {
        let window = visibleSpan
        if let playheadSource = projection.sourceTime(forComposition: Stamp(playhead)),
           window.contains(playheadSource) {
            return playheadSource
        }
        return window.stamp(atFraction: 0.5)
    }

    private func zoom(to duration: TimeInterval?, around anchor: Stamp<Source>) {
        guard let duration else {
            visibleDuration = nil
            viewportStart = 0
            return
        }
        visibleDuration = duration
        viewportStart = max(0, min(anchor.seconds - duration / 2, recordingDuration - duration))
    }

    /// Moves the window without changing the zoom level.
    func scrollViewport(to start: TimeInterval) {
        guard let visibleDuration else { return }
        viewportStart = max(0, min(start, recordingDuration - visibleDuration))
    }

    /// Centres the window on a point in the recording, for jumping to something the user
    /// picked from a list rather than found on screen.
    func revealInViewport(_ stamp: Stamp<Source>) {
        guard let visibleDuration else { return }
        scrollViewport(to: stamp.seconds - visibleDuration / 2)
    }

    /// Brings the playhead back into view — offered as an action rather than done
    /// automatically, since automatic following is what caused the panning.
    func scrollToPlayhead() {
        guard
            let visibleDuration,
            let source = projection.sourceTime(forComposition: Stamp(playhead))
        else { return }
        scrollViewport(to: source.seconds - visibleDuration / 2)
    }

    var isPlayheadVisible: Bool {
        guard let source = projection.sourceTime(forComposition: Stamp(playhead)) else { return false }
        return visibleSpan.contains(source)
    }

    func zoomToFit() {
        visibleDuration = nil
        viewportStart = 0
        detailTask?.cancel()
        laneDetail = [:]
        laneDetailSpan = nil
    }

    /// Re-reads the visible window at display resolution when the cached 10ms envelope is too
    /// coarse to draw as a waveform.
    ///
    /// The window is already in source time, because the lane's axis is the recording's — so
    /// reaching the audio file is one subtraction of that lane's offset and nothing else. The
    /// previous version took a *composition* window and subtracted only the lane offset,
    /// skipping the time map: once anything was cut it read the wrong region and then indexed
    /// past the bucket array, so the lane silently drew nothing at any zoom level.
    func requestWaveformDetail(viewWidth: CGFloat) {
        let span = visibleSpan
        guard
            let bucketsPerSecond = WaveformDetailRequest.bucketsPerSecond(
                visibleDuration: span.duration,
                viewWidth: viewWidth,
                cachedBucketsPerSecond: WaveformPeaks.defaultBucketsPerSecond
            )
        else {
            if laneDetailSpan != nil {
                detailTask?.cancel()
                laneDetail = [:]
                laneDetailSpan = nil
            }
            return
        }

        if let existing = laneDetailSpan,
           abs(existing.start - span.start) < 0.001,
           abs(existing.end - span.end) < 0.001 {
            return
        }

        detailTask?.cancel()
        detailTask = Task { [weak self] in
            guard let self else { return }
            // Coalesced: zooming and scrolling ask for this repeatedly, and a read per event
            // would be wasted work.
            try? await Task.sleep(for: .milliseconds(80))
            guard !Task.isCancelled else { return }

            var fetched: [AudioLane: WaveformPeaks] = [:]
            for lane in AudioLane.allCases {
                guard let probe = self.probes.first(where: { $0.kind.lane == lane }) else { continue }

                // Source -> this lane's own audio file, the projection's only expression of it.
                let fileStart = self.projection.audioFileTime(forSource: span.start, lane: lane)
                let fileEnd = self.projection.audioFileTime(forSource: span.end, lane: lane)
                guard fileEnd > 0 else { continue }

                if let detail = await self.extractor.detail(
                    url: probe.url,
                    range: TimeSpan(start: max(0, fileStart), end: fileEnd),
                    bucketsPerSecond: bucketsPerSecond
                ) {
                    fetched[lane] = detail
                }
            }

            guard !Task.isCancelled else { return }
            self.laneDetail = fetched
            self.laneDetailSpan = span
        }
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
    ///
    /// Goes through the projection rather than reaching into `timeMap` directly, so this is
    /// not a second conversion site that can drift from the first.
    var playheadSourceStamp: Stamp<Source> {
        if let mapped = projection.sourceTime(forComposition: Stamp(playhead)) {
            return mapped
        }
        return projection.regions.last?.span.end ?? projection.recording.end
    }

    var playheadSourceTime: TimeInterval { playheadSourceStamp.seconds }

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

    var cameraStyle: PiPStyle { store?.document.cameraStyle ?? .plain }

    func setCameraStyle(_ style: PiPStyle) {
        apply(.setCameraStyle(style))
    }

    func setCameraShape(_ shape: PiPStyle.Shape) {
        var style = cameraStyle
        style.shape = shape
        // A rounded shape with no radius looks like a rectangle, which reads as the control
        // having done nothing.
        if shape == .rounded, style.cornerRadius <= 0 { style.cornerRadius = 0.2 }
        setCameraStyle(style)
    }

    func setLaneMuted(_ lane: AudioLane, _ muted: Bool) {
        apply(.setLaneMuted(lane: lane, muted: muted))
    }

    // MARK: - Keyboard

    /// Runs a resolved key command. Returns false when there was nothing to do, so the event
    /// monitor can pass the keystroke on rather than swallowing it.
    @discardableResult
    func perform(_ command: ReviewKeyCommand) -> Bool {
        switch command {
        case .togglePlayback:
            togglePlayback()
        case .cutSelection:
            guard selection != nil else { return false }
            cutSelection()
        case .clearSelection:
            guard selection != nil || selectedCutRegionID != nil else { return false }
            clearSelection()
        case .splitAtPlayhead:
            splitAtPlayhead()
        case .addMarker:
            addMarkerAtPlayhead()
        case .undo:
            guard store?.canUndo == true else { return false }
            store?.undo()
        case .redo:
            guard store?.canRedo == true else { return false }
            store?.redo()
        case .zoomIn:
            guard canZoomIn else { return false }
            zoomIn()
        case .zoomOut:
            guard canZoomOut else { return false }
            zoomOut()
        case .zoomToFit:
            zoomToFit()
        case .nudgePlayhead(let frames):
            // Pause first: while playing, the next 30Hz tick overwrites the playhead and the
            // nudge is invisible — but the keystroke was still swallowed.
            pause()
            let step = Timeline.seconds(Timeline.frameDuration) * Double(frames)
            Task { await seek(to: playhead + Timeline.time(seconds: step), exact: true) }
        }
        return true
    }

    // MARK: - Selection

    var selectedCutRegion: ProjectedRegion? {
        guard let id = selectedCutRegionID else { return nil }
        return projection.regions.first { $0.id == id }
    }

    /// Selection is transient and lives only here: it must not persist, must not be undoable,
    /// and must not rebuild the composition.
    func select(from: Stamp<Source>, to: Stamp<Source>) {
        let span = StampSpan<Source>(
            start: Stamp(min(from.seconds, to.seconds)),
            end: Stamp(max(from.seconds, to.seconds))
        )
        guard span.duration > 0.001 else { return }
        selection = span
        selectedCutRegionID = nil
    }

    func clearSelection() {
        selection = nil
        selectedCutRegionID = nil
    }

    /// A click with no drag: seek there, and select a cut region if that is what was hit.
    ///
    /// A single click only *selects* a cut — restoring takes a second click. Restoring on one
    /// click would let a scrub accidentally un-cut a long range with nothing but a shade
    /// changing to show it.
    func handleLaneClick(at stamp: Stamp<Source>) {
        selection = nil

        if let region = projection.region(atSource: stamp), region.isCut {
            selectedCutRegionID = region.id
        } else {
            selectedCutRegionID = nil
        }

        // Inside a cut there is no composition time, so this lands on the cut's boundary —
        // the nearest point that actually exists on the edited timeline.
        guard let composition = projection.nearestCompositionTime(forSource: stamp) else { return }
        Task { await seek(to: composition.cm, exact: true) }
    }

    /// Removes the selected range. One cut, not merged into any it overlaps, so restoring it
    /// re-exposes whatever was underneath.
    func cutSelection() {
        guard let selection else { return }
        guard apply(.removeRange(selection.timeSpan)) else { return }
        clearSelection()
    }

    func splitAtSelectionStart() {
        guard let selection else { return }
        apply(.splitClip(at: selection.start.seconds))
    }

    func splitAtPlayhead() {
        apply(.splitClip(at: playheadSourceTime))
    }

    /// Restores every cut covering the selected region — plural, because a word cut can sit
    /// inside a range cut and removing only one would visibly do nothing.
    func restoreSelectedCutRegion() {
        guard let region = selectedCutRegion, !region.cutIDs.isEmpty else { return }
        guard apply(.uncut(ids: region.cutIDs)) else { return }
        selectedCutRegionID = nil
    }

    /// Double-clicking a cut region restores it directly.
    /// Restores a region already in hand, so a click on it does not have to be re-resolved
    /// through a coordinate — the 2pt-wide hairline a word cut draws as is narrower than the
    /// rounding in that round trip.
    func restoreCutRegion(_ region: ProjectedRegion) {
        guard region.isCut, !region.cutIDs.isEmpty else { return }
        apply(.uncut(ids: region.cutIDs))
        selectedCutRegionID = nil
    }

    func restoreCutRegion(at stamp: Stamp<Source>) {
        guard let region = projection.region(atSource: stamp), region.isCut else { return }
        apply(.uncut(ids: region.cutIDs))
        selectedCutRegionID = nil
    }

    // MARK: - Markers

    func addMarkerAtPlayhead(label: String = "") {
        apply(.addMarker(EditMarker(at: playheadSourceTime, label: label)))
    }

    /// Editorial markers only. A recording marker is a fact from `events.jsonl` and refuses to
    /// move or be renamed rather than silently forking into an editable copy.
    func moveMarker(_ marker: ProjectedMarker, to stamp: Stamp<Source>) {
        guard let id = marker.editorialID else {
            lastError = "Markers made while recording can't be moved."
            return
        }
        apply(.moveMarker(id: id, to: stamp.seconds))
    }

    func renameMarker(_ marker: ProjectedMarker, to label: String) {
        guard let id = marker.editorialID else {
            lastError = "Markers made while recording can't be renamed."
            return
        }
        apply(.renameMarker(id: id, label: label))
    }

    func removeMarker(_ marker: ProjectedMarker) {
        guard let id = marker.editorialID else {
            lastError = "Markers made while recording can't be deleted."
            return
        }
        apply(.removeMarker(id: id))
    }

    func seek(to marker: ProjectedMarker) {
        guard let composition = marker.composition else { return }
        Task { await seek(to: composition.cm, exact: true) }
    }

    // MARK: - Words

    var cutWordCount: Int { projection.words.filter(\.isCut).count }

    /// Cut or restore a single word. The projection already carries its source span, so no
    /// clock conversion happens here.
    func toggle(word: ProjectedWord) {
        guard let document = store?.document else { return }

        if document.isExcluded(wordID: word.id) {
            apply(.restoreWords(ids: [word.id]))
        } else if word.isCut {
            // Not cut by name but still absent — a coarse cut covers it. Restore whatever
            // covers it instead, which is what the user means by clicking it.
            let ids = projection.cutIDs(overlapping: word.source)
            guard !ids.isEmpty else { return }
            apply(.uncut(ids: ids))
        } else {
            apply(.excludeWords([ExcludedWord(
                id: word.id,
                start: word.source.start.seconds,
                end: word.source.end.seconds,
                text: word.text
            )]))
        }
    }

    func cut(cue: ProjectedCue) {
        apply(.removeRange(cue.source.timeSpan))
    }

    func addMarker(at stamp: Stamp<Source>, label: String = "") {
        apply(.addMarker(EditMarker(at: stamp.seconds, label: label)))
    }

    func seek(to cue: ProjectedCue) {
        guard let start = cue.composition.first?.start else { return }
        Task { await seek(to: start.cm, exact: true) }
    }

    func isWordExcluded(_ word: Transcript.Word) -> Bool {
        store?.document.isExcluded(wordID: word.id) ?? false
    }

    /// Cut or restore a single word from the transcript panel — the manual counterpart to the
    /// agent doing it, through the same operations.
    func toggleWord(_ word: Transcript.Word) {
        guard let document = store?.document else { return }

        if document.isExcluded(wordID: word.id) {
            apply(.restoreWords(ids: [word.id]))
        } else {
            let offset = transcriptOffset
            apply(.excludeWords([ExcludedWord(
                id: word.id,
                start: word.start + offset,
                end: word.end + offset,
                text: word.text
            )]))
        }
    }

    func restoreAllWords() {
        guard let ids = store?.document.excludedWords.map(\.id), !ids.isEmpty else { return }
        apply(.restoreWords(ids: ids))
    }

    var excludedWordCount: Int { store?.document.excludedWords.count ?? 0 }

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

    /// Seconds to add to a transcript time to get session time.
    ///
    /// Must equal the total offset the composition applies to the microphone lane, or a cut
    /// made from a transcript time lands somewhere other than the words it names. Computed
    /// from the resolved timeline rather than read from the document, so an automatic sync
    /// correction and a manual slip are both accounted for and a stale stored value can't
    /// desync the two.
    var transcriptOffset: TimeInterval {
        if let lane = timeline?.audio.first(where: { $0.lane == .microphone }) {
            return Timeline.seconds(lane.timeOffset)
        }
        return store?.document.micTimeOffset ?? 0
    }

    /// Composition time -> the clock the transcript is stamped in.
    ///
    /// Routed through the projection, which owns every clock conversion — reaching into
    /// `timeMap` here would be a second implementation of the same mapping.
    private func transcriptTime(forComposition time: CMTime) -> TimeInterval {
        guard let mapped = projection.sourceTime(forComposition: Stamp(time)) else { return 0 }
        return mapped.seconds - transcriptOffset
    }

    /// Seeks to where a cue starts on the edited timeline.
    ///
    /// Reads the already-projected cue instead of re-mapping the segment: the projection
    /// computed exactly this, and mapping it a second time here is how the two answers drift
    /// apart. A cue whose content was entirely cut has no composition span, so nothing moves.
    func seek(to segment: Transcript.Segment) {
        guard let start = projection.cues.first(where: { $0.id == segment.id })?
            .composition.first?.start else { return }
        Task { await seek(to: start.cm, exact: true) }
    }

    /// Removes the range a transcript cue occupies. The operation is expressed in session
    /// time, so it stays correct regardless of what has already been cut.
    func removeRange(of segment: Transcript.Segment) {
        let offset = transcriptOffset
        apply(.removeRange(TimeSpan(start: segment.start + offset, end: segment.end + offset)))
    }

    /// Re-derives every excluded word's span from the transcript.
    ///
    /// The id is the real handle; the stored span is a cache that lets `edit.json` play back
    /// without the transcript. Recomputing it whenever the transcript is available makes the
    /// pair self-healing — which matters because a build that converted transcript times to
    /// session times incorrectly baked wrong spans into saved documents, and those would
    /// otherwise keep cutting the wrong audio forever.
    private func reconcileExcludedWords() {
        guard let store, let transcript else { return }
        let identity = transcript.identity

        // A different transcript renumbers every word, so the saved ids no longer mean what
        // they meant. Re-deriving against it would move each cut onto whatever word now holds
        // that id — unrelated audio. Detach instead, before any re-derivation can run.
        if let recorded = store.document.transcriptIdentity, recorded != identity {
            detachWordCuts()
        }

        guard !store.document.excludedWords.isEmpty else {
            // Still worth stamping: it is what makes the *next* re-transcription detectable.
            stampTranscriptIdentity(identity)
            return
        }

        let byID = transcript.wordsByID
        let offset = transcriptOffset

        store.repair { document in
            document.cuts = document.cuts.map { cut in
                // Only word cuts are derived from the transcript; a range, filler or agent cut
                // has no word to re-derive from and must be left exactly as it is.
                guard case .word(let wordID, _) = cut.origin, let word = byID[wordID] else { return cut }

                var corrected = cut
                // Snap both sides and compare exactly. A tolerance here would have to be
                // looser than one tick (1/90000s), and anything looser can oscillate between
                // neighbouring ticks and rebuild the composition indefinitely.
                corrected.span = TimeSpan(
                    start: (try? SessionEdit.snapped(word.start + offset)) ?? cut.span.start,
                    end: (try? SessionEdit.snapped(word.end + offset)) ?? cut.span.end
                )
                corrected.origin = .word(id: wordID, text: word.text)
                return corrected
            }
            document.transcriptIdentity = identity
            // Unconditionally true, and NOT "did a span move".
            //
            // Gating on that dropped the identity stamp whenever the spans were already
            // correct — which is the common case, including every freshly migrated v1
            // document. The identity then stayed nil, the mismatch guard above could never
            // fire, and a later re-transcription silently re-derived every cut onto whatever
            // word had inherited its id. `repair` discards a no-op commit on its own via
            // `updated != document`, so there is nothing to save here anyway.
            return true
        }
    }

    /// Turns word cuts into plain range cuts, keeping the exact spans.
    ///
    /// The audio stays cut precisely where it was — the span is the authority for playback, and
    /// it was correct when authored. What is dropped is the claim that the cut corresponds to a
    /// particular transcript word, which is no longer true. The transcript panel stays
    /// consistent regardless, because it decides a word is cut from the geometry of the
    /// timeline rather than from these origins. And `uncut` still reverses them.
    private func detachWordCuts() {
        guard let store else { return }
        let affected = store.document.cuts.filter { $0.wordID != nil }.count
        guard affected > 0 else { return }

        store.repair { document in
            document.cuts = document.cuts.map { cut in
                guard cut.wordID != nil else { return cut }
                var detached = cut
                detached.origin = .range
                return detached
            }
            return true
        }

        // Surfaced rather than done quietly: the cuts still play exactly as before, but they
        // are no longer tied to transcript words, so the user should know why the transcript
        // stopped naming them. A notice, not an error — nothing went wrong.
        lastNotice = "The transcript was regenerated, so \(affected) word \(affected == 1 ? "cut" : "cuts") "
            + "\(affected == 1 ? "is" : "are") now a plain time \(affected == 1 ? "range" : "ranges"). "
            + "Nothing was un-cut — they just no longer follow the words."
    }

    private func stampTranscriptIdentity(_ identity: String) {
        guard let store, store.document.transcriptIdentity != identity else { return }
        store.repair { document in
            document.transcriptIdentity = identity
            return true
        }
    }

    private func loadTranscript() async {
        if let existing = Transcript.load(from: folder.transcriptURL) {
            transcript = existing
            transcriptState = .ready
            reconcileExcludedWords()
            reproject()
            return
        }

        guard probes.contains(where: { $0.kind == .microphone }) else { return }
        transcriptState = .transcribing

        do {
            let produced = try await SessionTranscriber().transcribe(
                microphoneURL: folder.microphoneURL,
                mediaDuration: Timeline.seconds(duration)
            )
            guard !Task.isCancelled else { return }
            produced.write(to: folder.transcriptURL)
            transcript = produced
            transcriptState = .ready
            reconcileExcludedWords()
            reproject()
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
    func buildDigest(detailRange: TimeSpan? = nil) -> SessionDigest? {
        guard let document = store?.document else { return nil }

        let digest = SessionDigest.make(
            sessionID: folder.id,
            duration: Timeline.seconds(duration),
            probes: probes,
            events: eventTimeline,
            document: document,
            transcript: transcript,
            transcriptOffset: transcriptOffset,
            // Word detail centres on the playhead when the whole transcript won't fit: that
            // is the part of the recording the user is actually looking at.
            focus: playheadSourceTime,
            detailRange: detailRange
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
            await self.converse(instruction: instruction, context: context, hopsRemaining: Self.maximumFetchHops)
        }
    }

    /// At most this many automatic follow-ups per request, so an agent that keeps asking for
    /// transcript can't loop indefinitely at the user's expense.
    private static let maximumFetchHops = 3

    /// One exchange, plus any follow-ups the agent asks for.
    private func converse(
        instruction: String,
        context: EditSuggestionContext,
        hopsRemaining: Int
    ) async {
        do {
            let result = try await suggester.suggest(instruction: instruction, context: context)
            guard !Task.isCancelled else { return }

            if !result.reply.isEmpty {
                conversation.append(AgentTurn(speaker: .agent, text: result.reply))
            }

            // Filler sweeps are resolved here rather than by the agent: Aura has the whole
            // word list, so it finds every instance instead of the handful the agent could
            // see in a trimmed digest.
            var resolved = result.suggestions
            let excluded = Set(store?.document.excludedWords.map(\.id) ?? [])
            for request in result.requests {
                if case .fillerSweep(let words, let span, let why) = request,
                   let suggestion = AgentRequestResolver.resolveFillerSweep(
                       words: words,
                       span: span,
                       why: why,
                       transcript: transcript,
                       micTimeOffset: transcriptOffset,
                       alreadyExcluded: excluded
                   ) {
                    resolved.append(suggestion)
                }
            }

            // Replaces rather than accumulates: a new answer supersedes the previous
            // proposal, and leaving stale operations pending invites applying edits the user
            // has already moved past.
            suggestions = resolved

            // If it asked for more transcript, answer it and let it continue.
            if
                hopsRemaining > 0,
                resolved.isEmpty,
                let wanted = result.requests.compactMap({ request -> TimeSpan? in
                    if case .transcript(let span) = request { return span }
                    return nil
                }).first,
                let document = store?.document
            {
                conversation.append(AgentTurn(
                    speaker: .user,
                    text: String(format: "(sending word detail for %.1f–%.1fs)", wanted.start, wanted.end)
                ))

                var next = context
                next = EditSuggestionContext(
                    sessionID: context.sessionID,
                    duration: context.duration,
                    transcript: context.transcript,
                    document: document,
                    markers: context.markers,
                    digest: buildDigest(detailRange: wanted),
                    fulfilling: wanted
                )
                await converse(
                    instruction: "Here is the word detail you asked for. Continue with the original request.",
                    context: next,
                    hopsRemaining: hopsRemaining - 1
                )
                return
            }

            agentState = .idle
        } catch {
            guard !Task.isCancelled else { return }
            agentState = .failed(error.localizedDescription)
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
