import AVFoundation
import CoreMedia

/// Owns a dedicated, webcam-only `AVCaptureSession` for `camera.mov`.
final class CameraRecorder: NSObject, @unchecked Sendable {
    private let session = AVCaptureSession()
    private let output = AVCaptureVideoDataOutput()
    private let queue = DispatchQueue(label: "com.innomightlabs.aura.camera")

    var onSampleBuffer: ((CMSampleBuffer) -> Void)?

    private static let discoveryDeviceTypes: [AVCaptureDevice.DeviceType] = [
        .builtInWideAngleCamera, .external, .continuityCamera, .deskViewCamera
    ]

    /// All connected cameras (built-in, external/USB, Continuity Camera, Desk View),
    /// for the menu bar's camera picker.
    static func availableDevices() -> [AVCaptureDevice] {
        AVCaptureDevice.DiscoverySession(
            deviceTypes: discoveryDeviceTypes,
            mediaType: .video,
            position: .unspecified
        ).devices
    }

    private static func resolveDevice(deviceID: String?) -> AVCaptureDevice? {
        if let deviceID, let match = AVCaptureDevice(uniqueID: deviceID) {
            return match
        }
        return AVCaptureDevice.default(for: .video)
    }

    /// Native pixel dimensions of the given camera's (or the default camera's) active
    /// format, for `camera.mov`'s `AVAssetWriterInput` output settings. Reading
    /// `activeFormat` does not require the session to be running.
    static func devicePixelSize(deviceID: String?) -> CGSize? {
        guard let device = resolveDevice(deviceID: deviceID) else { return nil }
        let dimensions = CMVideoFormatDescriptionGetDimensions(device.activeFormat.formatDescription)
        return CGSize(width: CGFloat(dimensions.width), height: CGFloat(dimensions.height))
    }

    func start(deviceID: String?) throws {
        guard let device = Self.resolveDevice(deviceID: deviceID) else {
            throw RecordingError.writerSetupFailed("No camera device found")
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

extension CameraRecorder: AVCaptureVideoDataOutputSampleBufferDelegate {
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        onSampleBuffer?(sampleBuffer)
    }
}
