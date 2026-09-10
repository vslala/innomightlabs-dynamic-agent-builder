import CoreMedia
import Foundation

/// The affine transform that places a source video layer into a destination rect.
///
/// Pure, and deliberately aspect-**fit** only. Aspect-fill would need
/// `setCropRectangle`, and the SDK specifies the crop rect's coordinate space but not
/// whether the cropped region keeps its in-frame offset or re-origins to (0,0) — a question
/// to settle with a rendered golden frame rather than a guess. Fitting into a rect the UI
/// already keeps at the camera's own aspect ratio makes the difference invisible anyway, and
/// keeps geometry to pure scale-and-translate.
enum PiPGeometry {
    /// - Parameters:
    ///   - displaySize: the source's upright size, i.e. `naturalSize` with
    ///     `preferredTransform` already applied.
    ///   - preferredTransform: applied first, since `insertTimeRange` does not carry it onto
    ///     the composition track — the layer transform is the single owner of geometry.
    ///   - destination: where the layer should land, in render-size coordinates, top-left origin.
    static func transform(
        displaySize: CGSize,
        preferredTransform: CGAffineTransform,
        destination: CGRect
    ) -> CGAffineTransform {
        guard
            displaySize.width > 0, displaySize.height > 0,
            destination.width > 0, destination.height > 0
        else { return preferredTransform }

        let scale = min(destination.width / displaySize.width, destination.height / displaySize.height)
        let drawn = CGSize(width: displaySize.width * scale, height: displaySize.height * scale)

        // `A.concatenating(B)` applies A then B: upright, then scale, then translate.
        // Positive translation moves the frame right and down.
        return preferredTransform
            .concatenating(CGAffineTransform(scaleX: scale, y: scale))
            .concatenating(CGAffineTransform(
                translationX: destination.minX + (destination.width - drawn.width) / 2,
                y: destination.minY + (destination.height - drawn.height) / 2
            ))
    }

    /// Playback and export get their own compositions from the same timeline, and the
    /// preview's render size is smaller: two HEVC decodes per composed frame (a Retina screen
    /// capture plus a camera) can drop frames. `renderScale` cannot do this — it is
    /// playback-only — so a reduced `renderSize` is the portable lever.
    static func renderSize(_ size: CGSize, maxDimension: CGFloat?) -> CGSize {
        guard let maxDimension, maxDimension >= 2 else { return size }
        let longest = max(size.width, size.height)
        guard longest > maxDimension else { return size }

        let scale = maxDimension / longest
        let even = { (value: CGFloat) in max(2, ((value * scale) / 2).rounded(.down) * 2) }
        return CGSize(width: even(size.width), height: even(size.height))
    }

    /// The rect a layer actually draws into after fitting — what the overlay UI needs in
    /// order to draw handles around the video rather than around its destination box.
    static func fittedRect(displaySize: CGSize, destination: CGRect) -> CGRect {
        guard
            displaySize.width > 0, displaySize.height > 0,
            destination.width > 0, destination.height > 0
        else { return destination }

        let scale = min(destination.width / displaySize.width, destination.height / displaySize.height)
        let drawn = CGSize(width: displaySize.width * scale, height: displaySize.height * scale)
        return CGRect(
            x: destination.minX + (destination.width - drawn.width) / 2,
            y: destination.minY + (destination.height - drawn.height) / 2,
            width: drawn.width,
            height: drawn.height
        )
    }
}
