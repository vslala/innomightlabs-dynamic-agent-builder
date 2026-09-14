import AVFoundation
import CoreMedia
import CoreVideo

/// How much camera resolution this recording justifies. Chosen by `CaptureSourceFactory`,
/// because only the profile knows whether the camera is the frame or a corner of it.
enum CameraQuality: Equatable, Sendable {
    /// The camera is the whole frame (no screen track).
    case primary
    /// The camera is a corner overlay, typically a quarter of the frame's width.
    case overlay

    var preset: AVCaptureSession.Preset {
        switch self {
        case .primary: return .hd1920x1080
        case .overlay: return .hd1280x720
        }
    }

    /// The camera is the frame unless a screen track will be under it.
    init(profile: RecordingProfile) {
        self = profile.tracks.contains(.screen) ? .overlay : .primary
    }
}

/// Owns a dedicated, webcam-only `AVCaptureSession` for `camera.mov`.
final class CameraCaptureSource: NSObject, CaptureSource, @unchecked Sendable {
    private let session = AVCaptureSession()
    private let output = AVCaptureVideoDataOutput()
    private let queue = DispatchQueue(label: "com.innomightlabs.aura.camera")

    private let deviceID: String?
    private let quality: CameraQuality
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

    init(deviceID: String?, quality: CameraQuality) {
        self.deviceID = deviceID
        self.quality = quality
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

    func prepare() async throws {
        try await CaptureAuthorization.request(.video, denied: .cameraPermissionDenied)

        guard let device = Self.resolveDevice(deviceID: deviceID) else {
            throw RecordingError.writerSetupFailed("No camera device found")
        }
        let input = try AVCaptureDeviceInput(device: device)

        session.beginConfiguration()
        if session.canSetSessionPreset(quality.preset) {
            session.sessionPreset = quality.preset
        }
        if session.canAddInput(input) {
            session.addInput(input)
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
            [.video(kind: .camera, url: context.folder.cameraURL, pixelSize: pixelSize ?? Self.fallbackPixelSize)],
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
