import Foundation

/// Seeds the camera overlay from the stretches the screen actually covers.
///
/// Where no screen segment covers the timeline the camera is the only picture, so it fills
/// the frame; where one does, it returns to its corner. Expressed as ordinary
/// `OverlayKeyframe`s — which is why nothing in the compositor needed to learn that profile
/// switching exists, and why the user can still drag, retime or delete any of them afterwards.
enum CameraOverlaySeed {
    static let fullFrame = NormalizedRect(x: 0, y: 0, width: 1, height: 1)

    /// `screenWindows` are the screen segments' spans in session time; need not be sorted or
    /// disjoint on input. Empty means no screen track at all, in which case the camera is
    /// already the base layer and a corner rect would be wrong, so a single full-frame
    /// keyframe is returned.
    static func keyframes(
        screenWindows: [TimeSpan],
        recordingDuration: TimeInterval,
        corner: NormalizedRect = .defaultCameraOverlay
    ) -> [OverlayKeyframe] {
        func clamped(_ t: TimeInterval) -> TimeInterval {
            Swift.min(Swift.max(0, t), recordingDuration)
        }

        let windows = screenWindows
            .map { (span: TimeSpan) -> TimeSpan in TimeSpan(start: clamped(span.start), end: clamped(span.end)) }
            .filter { $0.end > $0.start }
            .sorted { $0.start < $1.start }

        guard !windows.isEmpty else {
            return [OverlayKeyframe(t: 0, rect: fullFrame, visible: true)]
        }

        var keyframes: [OverlayKeyframe] = []
        var cursor: TimeInterval = 0

        for window in windows {
            // Windows are expected disjoint; an overlapping one is folded into the one
            // already open rather than emitting a redundant pair of keyframes inside it.
            guard window.start >= cursor else {
                cursor = max(cursor, window.end)
                continue
            }
            if window.start > cursor {
                keyframes.append(OverlayKeyframe(t: cursor, rect: fullFrame, visible: true))
            }
            keyframes.append(OverlayKeyframe(t: window.start, rect: corner, visible: true))
            cursor = window.end
        }

        if cursor < recordingDuration {
            keyframes.append(OverlayKeyframe(t: cursor, rect: fullFrame, visible: true))
        }

        return keyframes
    }
}
