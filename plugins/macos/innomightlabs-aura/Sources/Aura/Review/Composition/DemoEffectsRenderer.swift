import CoreGraphics
import CoreImage
import Foundation

/// Draws a browser demo's cursor and click ripples over the screen picture.
///
/// Kept out of the compositor so the geometry (where in the output a point on the page lands) is
/// plain functions of values. The sprites are drawn once with Core Graphics and only scaled and
/// faded per frame, which keeps a 60 fps export cheap.
enum DemoEffectsRenderer {
    /// The cursor's height as a fraction of the output height, before `CursorStyle.scale`. Close
    /// to a real pointer on a 1080p recording, and readable once a video is shrunk to a thumbnail.
    static let cursorHeightFraction = 0.04
    /// A ripple's diameter at its start and end, as a fraction of the output height.
    static let rippleDiameterFractions = (start: 0.03, end: 0.12)

    /// The part of the **source** frame in view: the crop, narrowed by the zoom. Both are
    /// top-left-origin and normalized, but the zoom is against the crop and the result against
    /// the source, which is what the picture is cut from and what the pointer path is in.
    static func sourceRegion(crop: NormalizedRect, zoom: NormalizedRect) -> NormalizedRect {
        NormalizedRect(
            x: crop.x + zoom.x * crop.width,
            y: crop.y + zoom.y * crop.height,
            width: zoom.width * crop.width,
            height: zoom.height * crop.height
        )
    }

    /// Where a source-normalized point lands on the placed picture, in Core Image's bottom-left
    /// space. Nil when it is well outside what is in view, so a zoomed-in frame draws no cursor
    /// that is off in the margin.
    static func renderPoint(for point: CGPoint, region: NormalizedRect, placed: CGRect) -> CGPoint? {
        guard region.width > 0, region.height > 0 else { return nil }
        let u = (point.x - region.x) / region.width
        let v = (point.y - region.y) / region.height
        guard (-0.1...1.1).contains(u), (-0.1...1.1).contains(v) else { return nil }
        return CGPoint(x: placed.minX + u * placed.width, y: placed.minY + (1 - v) * placed.height)
    }

    static func drawCursor(
        over image: CIImage,
        placed: CGRect,
        crop: NormalizedRect,
        zoom: NormalizedRect,
        effects: ResolvedDemoEffects,
        sessionTime: TimeInterval,
        renderSize: CGSize
    ) -> CIImage {
        guard let path = effects.cursor else { return image }
        let region = sourceRegion(crop: crop, zoom: zoom)
        var result = image

        if effects.cursorStyle.ripple {
            for ripple in path.ripples(at: sessionTime) {
                guard let center = renderPoint(for: ripple.position, region: region, placed: placed) else { continue }
                let eased = 1 - pow(1 - ripple.progress, 3)
                let fractions = rippleDiameterFractions
                let diameter = renderSize.height * (fractions.start + (fractions.end - fractions.start) * eased)
                result = place(
                    rippleSprite, center: center, size: CGSize(width: diameter, height: diameter),
                    anchor: CGPoint(x: 0.5, y: 0.5), alpha: 1 - ripple.progress, over: result
                )
            }
        }

        if let position = path.position(at: sessionTime),
           let tip = renderPoint(for: position, region: region, placed: placed) {
            let height = renderSize.height * cursorHeightFraction * effects.cursorStyle.scale
            let size = CGSize(width: height * cursorAspect, height: height)
            result = place(cursorSprite, center: tip, size: size, anchor: CGPoint(x: 0, y: 1), alpha: 1, over: result)
        }
        return result
    }

    /// `anchor` is the point of the sprite that sits on `center`, in the sprite's own unit square
    /// with a bottom-left origin: (0.5, 0.5) for a ripple, the top-left tip (0, 1) for the cursor.
    private static func place(
        _ sprite: CIImage, center: CGPoint, size: CGSize, anchor: CGPoint, alpha: Double, over image: CIImage
    ) -> CIImage {
        guard size.width > 0, size.height > 0, alpha > 0 else { return image }
        let extent = sprite.extent
        var placed = sprite
            .transformed(by: CGAffineTransform(scaleX: size.width / extent.width, y: size.height / extent.height))
            .transformed(by: CGAffineTransform(
                translationX: center.x - anchor.x * size.width,
                y: center.y - anchor.y * size.height
            ))
        if alpha < 1 {
            placed = placed.applyingFilter("CIColorMatrix", parameters: ["inputAVector": CIVector(x: 0, y: 0, z: 0, w: alpha)])
        }
        return placed.composited(over: image)
    }

    // MARK: - Sprites

    private static let cursorAspect = 14.0 / 21.0

    private static let cursorSprite: CIImage = makeCursorSprite()
    private static let rippleSprite: CIImage = makeRippleSprite()

    private static func makeSprite(width: Int, height: Int, draw: (CGContext) -> Void) -> CIImage {
        guard let context = CGContext(
            data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return CIImage.empty() }
        context.setAllowsAntialiasing(true)
        draw(context)
        return context.makeImage().map { CIImage(cgImage: $0) } ?? CIImage.empty()
    }

    /// The classic arrow, drawn with its tip at the top-left of the sprite.
    private static func makeCursorSprite() -> CIImage {
        let unit = 8.0
        let width = Int(14 * unit), height = Int(21 * unit)
        return makeSprite(width: width, height: height) { context in
            // Points in the arrow's own y-down units, flipped into Core Graphics' y-up space.
            let outline: [(Double, Double)] = [(0, 0), (0, 17), (4.5, 13), (7.5, 20), (10, 19), (7, 12.5), (13, 12.5)]
            let path = CGMutablePath()
            for (index, point) in outline.enumerated() {
                let p = CGPoint(x: 0.6 * unit + point.0 * unit, y: Double(height) - (0.6 * unit + point.1 * unit))
                index == 0 ? path.move(to: p) : path.addLine(to: p)
            }
            path.closeSubpath()
            context.setLineJoin(.round)
            context.addPath(path)
            context.setStrokeColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
            context.setLineWidth(1.4 * unit)
            context.strokePath()
            context.addPath(path)
            context.setFillColor(CGColor(red: 0.07, green: 0.07, blue: 0.09, alpha: 1))
            context.fillPath()
        }
    }

    private static func makeRippleSprite() -> CIImage {
        let side = 256
        return makeSprite(width: side, height: side) { context in
            let inset = 12.0
            let rect = CGRect(x: inset, y: inset, width: Double(side) - 2 * inset, height: Double(side) - 2 * inset)
            context.setFillColor(CGColor(red: 0.20, green: 0.50, blue: 1.0, alpha: 0.16))
            context.fillEllipse(in: rect)
            context.setStrokeColor(CGColor(red: 0.20, green: 0.50, blue: 1.0, alpha: 0.95))
            context.setLineWidth(10)
            context.strokeEllipse(in: rect)
        }
    }
}
