import CoreGraphics
import Foundation

/// Maps between a viewport position and a scrollbar thumb.
///
/// Pure, because the awkward part is not the drawing but the arithmetic: a thumb has a minimum
/// width, so its travel is shorter than the track, and the mapping in each direction has to
/// agree about that or dragging the thumb drifts away from the cursor.
enum ScrollBarGeometry {
    /// Small enough not to dominate a zoomed-in timeline, wide enough to grab. At 0.5s visible
    /// out of 400s the proportional thumb would be under a pixel.
    static let minimumThumbWidth: CGFloat = 32

    struct Thumb: Equatable {
        let x: CGFloat
        let width: CGFloat
    }

    /// Nil when there is nothing to scroll — the whole recording already fits.
    static func thumb(
        viewportStart: TimeInterval,
        visibleDuration: TimeInterval,
        recordingDuration: TimeInterval,
        trackWidth: CGFloat
    ) -> Thumb? {
        guard trackWidth > 0, recordingDuration > 0, visibleDuration > 0 else { return nil }
        guard visibleDuration < recordingDuration else { return nil }

        let proportional = trackWidth * CGFloat(visibleDuration / recordingDuration)
        let width = min(trackWidth, max(minimumThumbWidth, proportional))

        let scrollable = recordingDuration - visibleDuration
        let progress = scrollable > 0 ? min(1, max(0, viewportStart / scrollable)) : 0
        // Travel, not the full track: the thumb's own width is unavailable to it.
        let travel = trackWidth - width

        return Thumb(x: travel * CGFloat(progress), width: width)
    }

    /// The viewport start a thumb position implies — the inverse of `thumb`.
    static func viewportStart(
        thumbX: CGFloat,
        thumbWidth: CGFloat,
        visibleDuration: TimeInterval,
        recordingDuration: TimeInterval,
        trackWidth: CGFloat
    ) -> TimeInterval {
        let scrollable = max(0, recordingDuration - visibleDuration)
        let travel = trackWidth - thumbWidth
        guard travel > 0, scrollable > 0 else { return 0 }

        let progress = min(1, max(0, Double(thumbX / travel)))
        return progress * scrollable
    }
}
