import AVFoundation
import CoreImage
import CoreMedia
import Foundation

/// Per-instruction data for `CoreImagePiPCompositor`.
///
/// Everything the compositor needs rides on the instruction because AVFoundation instantiates
/// the compositor class itself, via `init()` — it can hold no constructor state.
final class PiPCompositionInstruction: NSObject, AVVideoCompositionInstructionProtocol {
    let timeRange: CMTimeRange
    let enablePostProcessing = false
    let containsTweening = false
    let requiredSourceTrackIDs: [NSValue]?
    let passthroughTrackID: CMPersistentTrackID

    let baseTrackID: CMPersistentTrackID
    let overlayTrackID: CMPersistentTrackID?
    /// Top-left origin, in render-size coordinates.
    let overlayRect: CGRect
    let overlayOpacity: Double
    let renderSize: CGSize
    let style: PiPStyle

    init(
        timeRange: CMTimeRange,
        baseTrackID: CMPersistentTrackID,
        overlayTrackID: CMPersistentTrackID?,
        overlayRect: CGRect,
        overlayOpacity: Double,
        renderSize: CGSize,
        style: PiPStyle
    ) {
        self.timeRange = timeRange
        self.baseTrackID = baseTrackID
        self.overlayTrackID = overlayTrackID
        self.overlayRect = overlayRect
        self.overlayOpacity = overlayOpacity
        self.renderSize = renderSize
        self.style = style
        requiredSourceTrackIDs = ([baseTrackID] + [overlayTrackID].compactMap { $0 })
            .map { NSNumber(value: $0) }
        // Never a passthrough: even with the overlay hidden the base may need scaling into
        // the render size.
        passthroughTrackID = kCMPersistentTrackID_Invalid
        super.init()
    }
}

/// Renders the camera overlay with a shape, border, and shadow — none of which the built-in
/// compositor can do, since it offers only an affine transform, opacity, and a rectangular
/// crop.
///
/// Used only when `PiPStyle` actually asks for something beyond a plain rectangle; the
/// layer-instruction path stays in place for the common case because it is markedly cheaper.
final class CoreImagePiPCompositor: NSObject, AVVideoCompositing {
    /// BGRA rather than YUV: Core Image works in RGB, and this avoids a conversion per frame.
    let sourcePixelBufferAttributes: [String: any Sendable]? = [
        kCVPixelBufferPixelFormatTypeKey as String: [kCVPixelFormatType_32BGRA],
        kCVPixelBufferMetalCompatibilityKey as String: true
    ]

    let requiredPixelBufferAttributesForRenderContext: [String: any Sendable] = [
        kCVPixelBufferPixelFormatTypeKey as String: [kCVPixelFormatType_32BGRA],
        kCVPixelBufferMetalCompatibilityKey as String: true
    ]

    private let queue = DispatchQueue(label: "com.innomightlabs.aura.pip-compositor")
    private let context = CIContext(options: [.useSoftwareRenderer: false])
    private var renderContext: AVVideoCompositionRenderContext?

    func renderContextChanged(_ newRenderContext: AVVideoCompositionRenderContext) {
        queue.sync { renderContext = newRenderContext }
    }

    func startRequest(_ request: AVAsynchronousVideoCompositionRequest) {
        queue.async { [weak self] in
            guard let self else { return }
            guard
                let instruction = request.videoCompositionInstruction as? PiPCompositionInstruction,
                let destination = request.renderContext.newPixelBuffer()
            else {
                request.finish(with: NSError(domain: "com.innomightlabs.aura", code: -1, userInfo: [
                    NSLocalizedDescriptionKey: "The compositor received an instruction it can't render."
                ]))
                return
            }

            let renderSize = request.renderContext.size
            var image = CIImage(color: .black).cropped(to: CGRect(origin: .zero, size: renderSize))

            if let base = request.sourceFrame(byTrackID: instruction.baseTrackID) {
                image = Self.fitted(CIImage(cvPixelBuffer: base), into: renderSize).composited(over: image)
            }

            if
                let overlayTrackID = instruction.overlayTrackID,
                instruction.overlayOpacity > 0,
                let overlay = request.sourceFrame(byTrackID: overlayTrackID)
            {
                image = PiPMask.compose(
                    base: image,
                    overlay: CIImage(cvPixelBuffer: overlay),
                    destination: instruction.overlayRect,
                    renderSize: renderSize,
                    style: instruction.style,
                    opacity: instruction.overlayOpacity
                )
            }

            self.context.render(image, to: destination)
            request.finish(withComposedVideoFrame: destination)
        }
    }

    func cancelAllPendingVideoCompositionRequests() {}

    /// Aspect-fits a source frame into the render size and centres it, matching what the
    /// layer-instruction path does for the base layer.
    private static func fitted(_ image: CIImage, into renderSize: CGSize) -> CIImage {
        let extent = image.extent
        guard extent.width > 0, extent.height > 0 else { return image }

        let scale = min(renderSize.width / extent.width, renderSize.height / extent.height)
        let scaled = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        return scaled.transformed(by: CGAffineTransform(
            translationX: (renderSize.width - scaled.extent.width) / 2 - scaled.extent.minX,
            y: (renderSize.height - scaled.extent.height) / 2 - scaled.extent.minY
        ))
    }
}
