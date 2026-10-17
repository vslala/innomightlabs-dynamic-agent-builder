import CoreGraphics
import CoreMedia
import CoreVideo
import Foundation
import ScreenCaptureKit

struct ChromeWindowLocator {
    enum LocatorError: Error, LocalizedError, Equatable {
        case invalidRequest, notFound, ambiguous, captureUnavailable, missingFrame
        var errorDescription: String? {
            switch self {
            case .invalidRequest: "The browser process or requested window size is invalid."
            case .notFound: "The Chrome recording window is not visible at the requested size."
            case .ambiguous: "More than one Chrome window matches. Close the extra window and try again."
            case .captureUnavailable: "Chrome's window could not be accessed. Check Screen Recording permission."
            case .missingFrame: "Chrome did not provide a calibration frame. Try again."
            }
        }
    }

    /// Value-only selection lets tests cover PID/geometry without manufacturing SCWindow objects.
    struct Candidate: Equatable, Sendable {
        let windowID: CGWindowID
        let processID: Int32
        let frame: CGRect
        let isOnScreen: Bool
        let windowLayer: Int
    }

    static func selectWindowID(
        from candidates: [Candidate], processID: Int32, requestedSize: WindowSize, tolerance: Double = 8
    ) throws -> CGWindowID {
        guard processID > 0, requestedSize.width > 0, requestedSize.height > 0,
              tolerance.isFinite, tolerance >= 0 else { throw LocatorError.invalidRequest }
        let matching = candidates.filter {
            $0.processID == processID && $0.isOnScreen && $0.windowLayer == 0
                && $0.frame.width.isFinite && $0.frame.height.isFinite
                && abs($0.frame.width - Double(requestedSize.width)) <= tolerance
                && abs($0.frame.height - Double(requestedSize.height)) <= tolerance
        }
        guard !matching.isEmpty else { throw LocatorError.notFound }
        // Never guess based on a title (which can contain private content) or another Chrome PID.
        guard matching.count == 1 else { throw LocatorError.ambiguous }
        return matching[0].windowID
    }

    func locate(processID: Int32, requestedSize: WindowSize) async throws -> SCWindow {
        try Task.checkCancellation()
        let content: SCShareableContent
        do { content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true) }
        catch { try Task.checkCancellation(); throw LocatorError.captureUnavailable }
        try Task.checkCancellation()
        let candidates = content.windows.compactMap { window -> Candidate? in
            guard let application = window.owningApplication else { return nil }
            return Candidate(windowID: window.windowID, processID: application.processID,
                             frame: window.frame, isOnScreen: window.isOnScreen, windowLayer: window.windowLayer)
        }
        let id = try Self.selectWindowID(from: candidates, processID: processID, requestedSize: requestedSize)
        guard let window = content.windows.first(where: { $0.windowID == id }) else { throw LocatorError.notFound }
        return window
    }

    /// Call explicitly after showCalibrationPage(), never in the background. Use the same pixel
    /// size as the recording configuration so calibration and the recorded frames share a mapping.
    @MainActor
    func captureFrame(window: SCWindow, pixelSize: CGSize) async throws -> CVPixelBuffer {
        guard pixelSize.width.isFinite, pixelSize.height.isFinite,
              pixelSize.width >= 1, pixelSize.height >= 1,
              pixelSize.width <= 16384, pixelSize.height <= 16384 else { throw LocatorError.invalidRequest }
        try Task.checkCancellation()
        let filter = SCContentFilter(desktopIndependentWindow: window)
        let configuration = SCStreamConfiguration()
        configuration.width = Int(pixelSize.width); configuration.height = Int(pixelSize.height)
        configuration.pixelFormat = kCVPixelFormatType_32BGRA
        // The display's default color space shifts the host's CSS marker RGB values.
        configuration.colorSpaceName = CGColorSpace.sRGB
        configuration.showsCursor = false
        configuration.ignoreShadowsSingleWindow = true
        configuration.capturesAudio = false
        let sample: CMSampleBuffer
        do { sample = try await SCScreenshotManager.captureSampleBuffer(contentFilter: filter, configuration: configuration) }
        catch { try Task.checkCancellation(); throw LocatorError.captureUnavailable }
        try Task.checkCancellation()
        guard let frame = CMSampleBufferGetImageBuffer(sample) else { throw LocatorError.missingFrame }
        return frame
    }
}
