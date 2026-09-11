import CoreImage
import CoreImage.CIFilterBuiltins
import Foundation

/// Draws the camera overlay's shape, border, and shadow with Core Image.
///
/// Separated from the compositor so the drawing can be exercised on a still image in a test,
/// rather than only through a live composition — the compositor's own contract (pixel buffer
/// pools, request lifecycle) is a different problem from whether a circle looks right.
enum PiPMask {
    /// Composites `overlay` onto `base` inside `destination`, styled.
    ///
    /// `destination` is in the base image's coordinate space, **top-left origin** to match the
    /// rest of the edit model; Core Image is bottom-left, so it is flipped here once.
    static func compose(
        base: CIImage,
        overlay: CIImage,
        destination: CGRect,
        renderSize: CGSize,
        style: PiPStyle,
        opacity: Double
    ) -> CIImage {
        guard opacity > 0, destination.width > 1, destination.height > 1 else { return base }

        let squared = drawnRect(for: style, in: destination)
        let flipped = CGRect(
            x: squared.minX,
            y: renderSize.height - squared.maxY,
            width: squared.width,
            height: squared.height
        )

        // Scale the camera to fill the destination, then crop to it: the overlay rect is kept
        // at the camera's aspect ratio by the UI, so this is a fit in practice.
        let extent = overlay.extent
        guard extent.width > 0, extent.height > 0 else { return base }
        let scale = max(flipped.width / extent.width, flipped.height / extent.height)

        var shaped = overlay
            .transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        shaped = shaped.transformed(by: CGAffineTransform(
            translationX: flipped.midX - shaped.extent.midX,
            y: flipped.midY - shaped.extent.midY
        ))
        shaped = shaped.cropped(to: flipped)

        let radius = cornerRadius(for: style, in: flipped)
        if radius > 0 {
            shaped = rounded(shaped, in: flipped, radius: radius)
        }

        var result = base

        if style.shadowOpacity > 0 {
            let shadowRadius = max(1, style.shadowRadius * min(flipped.width, flipped.height))
            result = drawShadow(
                under: shaped,
                in: flipped,
                radius: radius,
                blur: shadowRadius,
                opacity: style.shadowOpacity,
                onto: result
            )
        }

        if opacity < 1 {
            shaped = shaped.applyingFilter("CIColorMatrix", parameters: [
                "inputAVector": CIVector(x: 0, y: 0, z: 0, w: CGFloat(opacity))
            ])
        }

        result = shaped.composited(over: result)

        if style.borderWidth > 0 {
            result = drawBorder(in: flipped, radius: radius, style: style, opacity: opacity, onto: result)
        }

        return result.cropped(to: CGRect(origin: .zero, size: renderSize))
    }

    /// Where the overlay is actually drawn.
    ///
    /// A circle needs a square to be round: the overlay rect follows the camera's aspect
    /// ratio, so it is virtually never square, and max-rounding it directly produces a
    /// capsule. Squaring is therefore unavoidable — but it is **anchored to the rect's
    /// origin**, not centred. Centring meant an overlay placed at x = 0 did not touch the
    /// left edge, because the square was inset inside a wider rect. Anchoring keeps the rule
    /// the caller expects: the rect's origin is where the overlay starts.
    static func drawnRect(for style: PiPStyle, in destination: CGRect) -> CGRect {
        guard style.shape == .circle else { return destination }

        let side = min(destination.width, destination.height)
        return CGRect(x: destination.minX, y: destination.minY, width: side, height: side)
    }

    /// A circle is a rounded rect whose radius is half the shorter side — one code path
    /// instead of two, and it degrades correctly for a non-square overlay.
    static func cornerRadius(for style: PiPStyle, in rect: CGRect) -> CGFloat {
        let shorter = min(rect.width, rect.height)
        switch style.shape {
        case .rectangle:
            return 0
        case .rounded:
            return max(0, min(shorter / 2, CGFloat(style.cornerRadius) * shorter))
        case .circle:
            return shorter / 2
        }
    }

    /// Antialiased rounded-rect shape, used as the clip for the overlay.
    private static func shape(in rect: CGRect, radius: CGFloat, color: CIColor) -> CIImage? {
        let generator = CIFilter.roundedRectangleGenerator()
        generator.extent = rect
        generator.radius = Float(radius)
        generator.color = color
        return generator.outputImage?.cropped(to: rect)
    }

    /// Clips `image` to a rounded rect.
    ///
    /// `CISourceInCompositing` rather than `CIBlendWithAlphaMask` against an empty background:
    /// the latter leaves the masked-out region as white with zero alpha, which looks correct
    /// when rendered through a software context but composites as opaque white once the GPU
    /// path treats it as premultiplied. Source-in multiplies through the mask's alpha and so
    /// stays premultiplied-correct in both.
    private static func rounded(_ image: CIImage, in rect: CGRect, radius: CGFloat) -> CIImage {
        guard let mask = shape(in: rect, radius: radius, color: .white) else { return image }

        let masked = CIFilter.sourceInCompositing()
        masked.inputImage = image
        masked.backgroundImage = mask
        return masked.outputImage?.cropped(to: rect) ?? image
    }

    private static func drawShadow(
        under image: CIImage,
        in rect: CGRect,
        radius: CGFloat,
        blur: CGFloat,
        opacity: Double,
        onto background: CIImage
    ) -> CIImage {
        guard let shape = shape(
            in: rect,
            radius: radius,
            color: CIColor(red: 0, green: 0, blue: 0, alpha: CGFloat(min(1, opacity)))
        ) else { return background }

        let blurred = shape
            .clampedToExtent()
            .applyingFilter("CIGaussianBlur", parameters: ["inputRadius": blur])
            .cropped(to: rect.insetBy(dx: -blur * 2, dy: -blur * 2))

        return blurred.composited(over: background)
    }

    private static func drawBorder(
        in rect: CGRect,
        radius: CGFloat,
        style: PiPStyle,
        opacity: Double,
        onto background: CIImage
    ) -> CIImage {
        let width = max(1, CGFloat(style.borderWidth) * min(rect.width, rect.height))
        let components = style.borderColor.count >= 3 ? style.borderColor : [1, 1, 1]
        let color = CIColor(
            red: CGFloat(components[0]),
            green: CGFloat(components[1]),
            blue: CGFloat(components[2]),
            alpha: CGFloat(min(1, opacity))
        )

        // The ring is the outer shape with the inset shape knocked out of it, so a border on a
        // circle follows the curve rather than boxing it. Source-out keeps only where the
        // background (the inner shape) is transparent, and stays premultiplied-correct.
        let innerRect = rect.insetBy(dx: width, dy: width)
        guard
            let outerImage = shape(in: rect, radius: radius, color: color),
            let innerImage = shape(in: innerRect, radius: max(0, radius - width), color: .white)
        else { return background }

        let knockout = CIFilter.sourceOutCompositing()
        knockout.inputImage = outerImage
        knockout.backgroundImage = innerImage

        let ring = (knockout.outputImage ?? outerImage).cropped(to: rect)
        return ring.composited(over: background)
    }
}
