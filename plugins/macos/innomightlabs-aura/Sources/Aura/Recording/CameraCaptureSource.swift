import AVFoundation
import CoreMedia
import CoreVideo

/// Owns a dedicated, webcam-only `AVCaptureSession` for `camera.mov`.
///
/// Always records at `.hd1920x1080`. A profile switch can promote any camera track to full
/// frame at any point in the session (see Phase 7), and the preset cannot change once the
/// session is running without reconfiguring — and thereby interrupting — the capture. With no
/// safe moment left to choose a lower preset, there is no case where it is knowably sufficient.
final class CameraCaptureSource: NSObject, CaptureSource, @unchecked Sendable {
    private let session = AVCaptureSession()
    private let output = AVCaptureVideoDataOutput()
    private let queue = DispatchQueue(label: "com.innomightlabs.aura.camera")

    private let deviceID: String?
    /// Read from `activeFormat` after the session preset is applied in `prepare()`. Reading it
    /// before the preset applies is the defect this fixes: the declared size could disagree
    /// with what the session actually encodes.
    private var pixelSize: CGSize?

    let kinds: [TrackKind] = [.camera]
    private(set) var writers: [TrackKind: TrackWriter] = [:]
    var onFailure: (@Sendable (Error) -> Void)?

    /// Last-write-wins cache of the most recent frame, for `screenshot()`. Written on the
    /// capture queue, read on the main actor — `CVPixelBuffer` retain/release is thread-safe.
    private(set) var latestVideoFrame: CVPixelBuffer?

    private static let discoveryDeviceTypes: [AVCaptureDevice.DeviceType] = [
        .builtInWideAngleCamera, .external, .continuityCamera, .deskViewCamera
    ]

    private static let fallbackPixelSize = CGSize(width: 1280, height: 720)

    init(deviceID: String?) {
        self.deviceID = deviceID
    }

    /// All connected cameras (built-in, external/USB, Continuity Camera, Desk View), for the
    /// menu bar's camera picker.
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

    /// The largest format up to 1920 wide, preferring the most landscape one at equal width.
    /// Capped at 1080p to keep files and encoding cost bounded.
    private static func widestFormat(of device: AVCaptureDevice) -> AVCaptureDevice.Format? {
        let candidates = device.formats.map { format -> (format: AVCaptureDevice.Format, size: CMVideoDimensions) in
            (format, CMVideoFormatDescriptionGetDimensions(format.formatDescription))
        }.filter { $0.size.width <= 1920 && $0.size.width > $0.size.height }

        return candidates.max { a, b in
            if a.size.width != b.size.width { return a.size.width < b.size.width }
            return Double(a.size.width) / Double(a.size.height) < Double(b.size.width) / Double(b.size.height)
        }?.format
    }

    func prepare() async throws {
        try await CaptureAuthorization.request(.video, denied: .cameraPermissionDenied)

        guard let device = Self.resolveDevice(deviceID: deviceID) else {
            throw RecordingError.writerSetupFailed("No camera device found")
        }
        let input = try AVCaptureDeviceInput(device: device)

        session.beginConfiguration()
        if session.canAddInput(input) {
            session.addInput(input)
        }
        // A preset lets the camera fall back to a cropped or 4:3 format. Choosing the format
        // ourselves records whatever the camera natively offers at its widest.
        if let format = Self.widestFormat(of: device), (try? device.lockForConfiguration()) != nil {
            device.activeFormat = format  // on macOS this takes the session off any preset
            device.unlockForConfiguration()
        } else if session.canSetSessionPreset(.hd1920x1080) {
            session.sessionPreset = .hd1920x1080
        }
        output.setSampleBufferDelegate(self, queue: queue)
        if session.canAddOutput(output) {
            session.addOutput(output)
        }
        session.commitConfiguration()

        // Read *after* the preset applied, which is the whole reason configuration lives in
        // `prepare` and not in `start`.
        let dimensions = CMVideoFormatDescriptionGetDimensions(device.activeFormat.formatDescription)
        pixelSize = CGSize(width: CGFloat(dimensions.width), height: CGFloat(dimensions.height))
    }

    func start(context: CaptureContext) async throws {
        writers = try makeWriters(
            [.video(kind: .camera, url: context.outputURL(for: .camera), pixelSize: pixelSize ?? Self.fallbackPixelSize)],
            context: context
        )
        session.startRunning()
    }

    /// Stops the session and removes its input/output so a later `start()` (e.g. the
    /// next recording session) doesn't fail trying to re-add a device already attached.
    func stop() async {
        session.stopRunning()
        session.beginConfiguration()
        session.inputs.forEach { session.removeInput($0) }
        session.outputs.forEach { session.removeOutput($0) }
        session.commitConfiguration()
    }

    func cancel() {
        session.stopRunning()
    }
}

extension CameraCaptureSource: AVCaptureVideoDataOutputSampleBufferDelegate {
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        if let imageBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) {
            latestVideoFrame = imageBuffer
        }
        writers[.camera]?.append(sampleBuffer)
    }
}
