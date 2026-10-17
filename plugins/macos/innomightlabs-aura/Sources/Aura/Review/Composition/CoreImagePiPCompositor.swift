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
    let requiredSourceTrackIDs: [NSValue]?
    let passthroughTrackID: CMPersistentTrackID

    let baseTrackID: CMPersistentTrackID
    let overlayTrackID: CMPersistentTrackID?
    /// Top-left origin, in render-size coordinates.
    let overlayRect: CGRect
    let overlayOpacity: Double
    let renderSize: CGSize
    let style: PiPStyle
    let screenCrop: NormalizedRect?
    let effects: ResolvedDemoEffects?
    /// Zoom and the cursor move every frame, which AVFoundation must be told or it may reuse one.
    var containsTweening: Bool { effects != nil }

    init(
        timeRange: CMTimeRange,
        baseTrackID: CMPersistentTrackID,
        overlayTrackID: CMPersistentTrackID?,
        overlayRect: CGRect,
        overlayOpacity: Double,
        renderSize: CGSize,
        style: PiPStyle,
        screenCrop: NormalizedRect? = nil,
        effects: ResolvedDemoEffects? = nil
    ) {
        self.timeRange = timeRange
        self.baseTrackID = baseTrackID
        self.overlayTrackID = overlayTrackID
        self.overlayRect = overlayRect
        self.overlayOpacity = overlayOpacity
        self.renderSize = renderSize
        self.style = style
        self.screenCrop = screenCrop
        self.effects = effects
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
/// Used for source-frame screen crops or a `PiPStyle` beyond a plain rectangle; the
/// layer-instruction path stays in place for the common unstyled, uncropped case.
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
                let frame = Self.demoFrame(for: instruction, at: request.compositionTime)
                let screen = Self.screenImage(CIImage(cvPixelBuffer: base), crop: instruction.screenCrop,
                                              zoom: frame.zoom, renderSize: renderSize)
                image = screen.composited(over: image)
                if let effects = instruction.effects, let time = frame.sessionTime {
                    image = DemoEffectsRenderer.drawCursor(
                        over: image, placed: screen.extent, crop: instruction.screenCrop ?? SessionEdit.fullFrame,
                        zoom: frame.zoom, effects: effects, sessionTime: time, renderSize: renderSize
                    )
                }
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

    /// The zoom in force and the session time it is for, at one composition time.
    static func demoFrame(
        for instruction: PiPCompositionInstruction, at compositionTime: CMTime
    ) -> (zoom: NormalizedRect, sessionTime: TimeInterval?) {
        guard let effects = instruction.effects,
              let source = effects.timeMap.sourceTime(forComposition: compositionTime) else {
            return (SessionEdit.fullFrame, nil)
        }
        let time = Timeline.seconds(source)
        return (ZoomTrack.rect(at: time, in: effects.zooms), time)
    }

    /// Convert the edit's top-left source rect to Core Image's bottom-left space before
    /// fitting. Cropping first ensures toolbar pixels cannot leak into preview or export. The
    /// zoom then narrows the crop, so a zoomed frame is cut from the source, not scaled up from
    /// the cropped picture.
    static func screenImage(
        _ image: CIImage, crop: NormalizedRect?, zoom: NormalizedRect = SessionEdit.fullFrame, renderSize: CGSize
    ) -> CIImage {
        guard crop != nil || zoom != SessionEdit.fullFrame else { return fitted(image, into: renderSize) }
        let extent = image.extent
        let region = DemoEffectsRenderer.sourceRegion(crop: crop ?? SessionEdit.fullFrame, zoom: zoom)
        let rect = CGRect(
            x: extent.minX + region.x * extent.width,
            y: extent.minY + (1 - region.y - region.height) * extent.height,
            width: region.width * extent.width,
            height: region.height * extent.height
        )
        return fitted(image.cropped(to: rect), into: renderSize)
    }

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
