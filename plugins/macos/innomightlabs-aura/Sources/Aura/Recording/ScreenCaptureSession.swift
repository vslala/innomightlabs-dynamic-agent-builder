import ScreenCaptureKit
import CoreMedia
import CoreVideo

/// Owns the single `SCStream` used for both `screen.mov` and `system-audio.m4a`.
/// Distributes sample buffers via callbacks; does not write any files itself.
final class ScreenCaptureSession: NSObject, @unchecked Sendable {
    private var stream: SCStream?

    var onVideoSampleBuffer: ((CMSampleBuffer) -> Void)?
    var onAudioSampleBuffer: ((CMSampleBuffer) -> Void)?
    var onStreamStopped: ((Error) -> Void)?

    private let videoQueue = DispatchQueue(label: "com.innomightlabs.aura.screencapture.video")
    private let audioQueue = DispatchQueue(label: "com.innomightlabs.aura.screencapture.audio")

    func start(target: CaptureTarget) async throws {
        let filter = target.contentFilter()

        let pixelSize = target.pixelSize
        let configuration = SCStreamConfiguration()
        configuration.width = Int(pixelSize.width)
        configuration.height = Int(pixelSize.height)
        configuration.minimumFrameInterval = CMTime(value: 1, timescale: 30)
        configuration.queueDepth = 5
        configuration.pixelFormat = kCVPixelFormatType_32BGRA
        configuration.showsCursor = true
        configuration.capturesAudio = true
        configuration.excludesCurrentProcessAudio = true

        let stream = SCStream(filter: filter, configuration: configuration, delegate: self)
        try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: videoQueue)
        try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: audioQueue)
        try await stream.startCapture()
        self.stream = stream
    }

    func stop() async throws {
        guard let stream else { return }
        try await stream.stopCapture()
        self.stream = nil
    }
}

extension ScreenCaptureSession: SCStreamOutput {
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard CMSampleBufferDataIsReady(sampleBuffer) else { return }
        switch type {
        case .screen:
            // ScreenCaptureKit also delivers periodic non-.complete frames (idle/blank/
            // suspended/started) with no real new pixel data whenever the screen content
            // isn't actively changing. Appending one of those to AVAssetWriterInput
            // corrupts the encoder pipeline, so only forward genuinely complete frames.
            guard Self.isCompleteFrame(sampleBuffer) else { return }
            onVideoSampleBuffer?(sampleBuffer)
        case .audio:
            onAudioSampleBuffer?(sampleBuffer)
        default:
            break
        }
    }

    private static func isCompleteFrame(_ sampleBuffer: CMSampleBuffer) -> Bool {
        guard let attachmentsArray = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
              let attachments = attachmentsArray.first,
              let statusRawValue = attachments[.status] as? Int,
              let status = SCFrameStatus(rawValue: statusRawValue) else {
            return false
        }
        return status == .complete
    }
}

extension ScreenCaptureSession: SCStreamDelegate {
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        onStreamStopped?(error)
    }
}
