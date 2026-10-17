import CoreGraphics
import Foundation

/// Turns what a browser take recorded into the edits that make it look like a finished demo.
///
/// Pure, like `CameraOverlaySeed`: values in, operations out. They are ordinary operations, so
/// the user can drag, retime, delete or undo any of them afterwards.
enum DemoEditSeed {
    /// The magnification a zoom on an element aims for. Enough to read small text, little enough
    /// that the page around the element stays recognisable.
    static let targetMagnification = 2.5
    /// The widest view a zoom may still be worth doing for. Past this the move is a wobble.
    static let maximumWorthwhileSide = 0.9
    /// Zoom starts a moment before the pointer arrives, so the viewer is looking when it lands.
    static let leadIn: TimeInterval = 0.3
    /// Two zooms closer than this are one camera move, not two: easing out and straight back in
    /// reads as a pump.
    static let mergeGap: TimeInterval = 0.8
    /// Zoom lingers after the step's last action so the result can be read.
    static let linger: TimeInterval = 0.5

    /// - Parameter recordingDuration: zooms are kept inside it, because the document refuses any
    ///   that run past the recording.
    static func operations(
        spec: DemoSpec,
        log: ActionLog,
        viewport: BrowserViewportMetadata,
        narration: [NarrationLine],
        recordingDuration: TimeInterval
    ) -> [EditOperation] {
        let zooms = merged(zoomSegments(spec: spec, log: log, viewport: viewport, recordingDuration: recordingDuration))
            .filter(\.isValid)
        return zooms.map(EditOperation.setZoom) + narration.map(EditOperation.setNarration)
    }

    // MARK: - Zoom

    static func zoomSegments(
        spec: DemoSpec,
        log: ActionLog,
        viewport: BrowserViewportMetadata,
        recordingDuration: TimeInterval
    ) -> [ZoomSegment] {
        let visible = viewport.viewportRect
        guard visible.width > 0, visible.height > 0 else { return [] }

        // Steps in the order they ran, each with the span of the log that belongs to it.
        let starts = log.entries.filter { $0.kind == .stepStart }
        func start(of stepID: String) -> TimeInterval? { starts.first { $0.stepID == stepID }?.t }
        func end(of stepID: String) -> (t: TimeInterval, rect: CGRect?)? {
            log.entries.last { $0.stepID == stepID && $0.kind == .stepEnd }.map { ($0.t, $0.rect) }
        }

        var segments: [ZoomSegment] = []
        for (index, step) in spec.steps.enumerated() {
            guard let begin = start(of: step.id), let finish = end(of: step.id) else { continue }
            // The zoom holds until the next step begins, which is after the narration for this one
            // has finished — the take was paced to it.
            let nextStart = spec.steps.dropFirst(index + 1).lazy.compactMap { start(of: $0.id) }.first
            let end = min(recordingDuration, max(finish.t + linger, (nextStart ?? finish.t + linger) - 0.1))
            let from = max(0, begin - leadIn)

            let rect: NormalizedRect?
            switch step.zoom {
            case .none: rect = nil
            case .region(let region): rect = NormalizedRect(x: region.x, y: region.y, width: region.width, height: region.height)
            case .target:
                rect = finish.rect.flatMap {
                    targetRegion(
                        for: viewport.windowRect(forCSSRect: BrowserRect(x: $0.minX, y: $0.minY, width: $0.width, height: $0.height)),
                        in: visible
                    )
                }
            }
            if let rect { segments.append(ZoomSegment(span: TimeSpan(start: from, end: end), rect: rect)) }
        }
        return segments
    }

    /// A same-aspect region around `element`, in the visible frame's normalized coordinates, or
    /// nil when the element is so large that zooming on it would barely move the picture.
    static func targetRegion(for element: CGRect, in visible: CGRect) -> NormalizedRect? {
        guard element.width > 0, element.height > 0 else { return nil }
        let normalizedWidth = element.width / visible.width
        let normalizedHeight = element.height / visible.height
        // Normalized against the frame, a region with the frame's own aspect ratio is square.
        let side = max(1 / ZoomSegment.maximumMagnification, max(normalizedWidth, normalizedHeight) * targetMagnification)
        guard side <= maximumWorthwhileSide else { return nil }
        let centerX = (element.midX - visible.minX) / visible.width
        let centerY = (element.midY - visible.minY) / visible.height
        return NormalizedRect(
            x: min(max(centerX - side / 2, 0), 1 - side),
            y: min(max(centerY - side / 2, 0), 1 - side),
            width: side,
            height: side
        )
    }

    /// Folds zooms that follow each other closely into one that frames both, so the camera makes
    /// one move rather than easing out and back in. A pair whose combined frame would be too wide
    /// to be worth zooming keeps only the first.
    static func merged(_ segments: [ZoomSegment]) -> [ZoomSegment] {
        var result: [ZoomSegment] = []
        for segment in segments.sorted(by: { $0.span.start < $1.span.start }) {
            guard var last = result.last, segment.span.start - last.span.end < mergeGap else {
                result.append(segment)
                continue
            }
            let left = min(last.rect.x, segment.rect.x)
            let top = min(last.rect.y, segment.rect.y)
            let right = max(last.rect.x + last.rect.width, segment.rect.x + segment.rect.width)
            let bottom = max(last.rect.y + last.rect.height, segment.rect.y + segment.rect.height)
            let side = max(right - left, bottom - top)
            guard side <= maximumWorthwhileSide else { continue }
            let centerX = (left + right) / 2, centerY = (top + bottom) / 2
            last.rect = NormalizedRect(
                x: min(max(centerX - side / 2, 0), 1 - side),
                y: min(max(centerY - side / 2, 0), 1 - side),
                width: side, height: side
            )
            last.span.end = max(last.span.end, segment.span.end)
            result[result.count - 1] = last
        }
        return result
    }
}

extension EditDocumentStore {
    /// Called when a browser take's review window opens, once. The marker is bookkeeping, not an
    /// effect, so it precedes the undo snapshot: undoing the seed removes the zooms and narration
    /// as one step without making the next open seed them again.
    @MainActor
    func seedDemoEffects(from folder: SessionFolder) {
        guard !document.hasSeededDemoEffects,
              let spec = try? JSONDecoder().decode(DemoSpec.self, from: Data(contentsOf: folder.demoSpecURL)),
              let viewport = try? JSONDecoder().decode(BrowserViewportMetadata.self, from: Data(contentsOf: folder.viewportURL)),
              let log = try? JSONDecoder().decode(ActionLog.self, from: Data(contentsOf: folder.actionLogURL)) else { return }
        let narration = (try? JSONDecoder().decode([NarrationLine].self, from: Data(contentsOf: folder.narrationLinesURL))) ?? []
        repair {
            $0.hasSeededDemoEffects = true
            return true
        }
        let operations = DemoEditSeed.operations(
            spec: spec, log: log, viewport: viewport, narration: narration,
            recordingDuration: document.recordingDuration
        )
        // One undo step, so a user who dislikes the polish removes all of it with one Cmd+Z.
        apply(operations)
    }
}

extension ReviewViewModel {
    static func loadCursorPath(from folder: SessionFolder) -> CursorPath? {
        guard let viewport = try? JSONDecoder().decode(BrowserViewportMetadata.self, from: Data(contentsOf: folder.viewportURL)),
              let log = try? JSONDecoder().decode(ActionLog.self, from: Data(contentsOf: folder.actionLogURL)) else { return nil }
        // A click ripples when its step asks for it, which is what the editor's toggle writes.
        let spec = try? JSONDecoder().decode(DemoSpec.self, from: Data(contentsOf: folder.demoSpecURL))
        let ripples = spec.map { Set($0.steps.filter { $0.emphasis == .ripple }.map(\.id)) }
        let path = CursorPath(log: log, viewport: viewport, rippleSteps: ripples)
        return path.isEmpty ? nil : path
    }

    /// Each step of a browser take with the stretch of the recording it played over: from its first
    /// action to just before the next step began, which is when its narration was playing.
    static func loadDemoSteps(from folder: SessionFolder) -> [SessionDigest.DemoStepSpan] {
        guard let spec = try? JSONDecoder().decode(DemoSpec.self, from: Data(contentsOf: folder.demoSpecURL)),
              let log = try? JSONDecoder().decode(ActionLog.self, from: Data(contentsOf: folder.actionLogURL)) else { return [] }
        let starts = spec.steps.compactMap { step in
            log.entries.first { $0.stepID == step.id && $0.kind == .stepStart }.map { (step, $0.t) }
        }
        return starts.enumerated().map { index, entry in
            let (step, start) = entry
            let end = index + 1 < starts.count
                ? starts[index + 1].1
                : (log.entries.last { $0.stepID == step.id && $0.kind == .stepEnd }?.t ?? start)
            return SessionDigest.DemoStepSpan(id: step.id, intent: step.intent, span: TimeSpan(start: start, end: max(end, start)))
        }
    }

    /// The narration clips that exist on disk, which is all the resolver may play.
    func availableNarrationClips(for document: SessionEdit) -> [UUID: URL] {
        var clips: [UUID: URL] = [:]
        for line in document.narration {
            let url = folder.narrationClipURL(for: line.id)
            if FileManager.default.fileExists(atPath: url.path) { clips[line.id] = url }
        }
        return clips
    }
}
