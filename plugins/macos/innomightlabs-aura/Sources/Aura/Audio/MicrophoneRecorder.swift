import AVFoundation
import CoreMedia

/// Owns a dedicated, mic-only `AVCaptureSession` for `microphone.m4a`.
final class MicrophoneRecorder: NSObject, @unchecked Sendable {
    private let session = AVCaptureSession()
    private let output = AVCaptureAudioDataOutput()
    private let queue = DispatchQueue(label: "com.innomightlabs.aura.microphone")

    var onSampleBuffer: ((CMSampleBuffer) -> Void)?

    func start() throws {
        guard let device = AVCaptureDevice.default(for: .audio) else {
            throw RecordingError.writerSetupFailed("No microphone device found")
        }
        let input = try AVCaptureDeviceInput(device: device)

        session.beginConfiguration()
        if session.canAddInput(input) {
            session.addInput(input)
        }
        output.setSampleBufferDelegate(self, queue: queue)
        if session.canAddOutput(output) {
            session.addOutput(output)
        }
        session.commitConfiguration()
        session.startRunning()
    }

    /// Stops the session and removes its input/output so a later `start()` (e.g. the
    /// next recording session) doesn't fail trying to re-add a device already attached.
    func stop() {
        session.stopRunning()
        session.beginConfiguration()
        session.inputs.forEach { session.removeInput($0) }
        session.outputs.forEach { session.removeOutput($0) }
        session.commitConfiguration()
    }
}

extension MicrophoneRecorder: AVCaptureAudioDataOutputSampleBufferDelegate {
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        onSampleBuffer?(sampleBuffer)
    }
}
