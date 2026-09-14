import AVFoundation
import CoreMedia

/// Owns a dedicated, mic-only `AVCaptureSession` for `microphone.m4a`.
final class MicrophoneCaptureSource: NSObject, CaptureSource, @unchecked Sendable {
    private let session = AVCaptureSession()
    private let output = AVCaptureAudioDataOutput()
    private let queue = DispatchQueue(label: "com.innomightlabs.aura.microphone")

    private let deviceID: String?

    let kinds: [TrackKind] = [.microphone]
    private(set) var writers: [TrackKind: TrackWriter] = [:]
    var onFailure: (@Sendable (Error) -> Void)?

    /// Written on the main actor, read on the capture queue. A stale read for one buffer is
    /// harmless — worst case one extra or missing sample at the mute boundary — unlike
    /// `PauseClock`, where exact correctness is required.
    private var isMuted = false

    init(deviceID: String?) {
        self.deviceID = deviceID
    }

    static func availableDevices() -> [AVCaptureDevice] {
        AVCaptureDevice.DiscoverySession(
            deviceTypes: [.microphone, .external],
            mediaType: .audio,
            position: .unspecified
        ).devices
    }

    private static func resolveDevice(deviceID: String?) -> AVCaptureDevice? {
        if let deviceID, let match = AVCaptureDevice(uniqueID: deviceID) {
            return match
        }
        return AVCaptureDevice.default(for: .audio)
    }

    func prepare() async throws {
        try await CaptureAuthorization.request(.audio, denied: .microphonePermissionDenied)

        guard let device = Self.resolveDevice(deviceID: deviceID) else {
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
    }

    func start(context: CaptureContext) async throws {
        writers = try makeWriters(
            [.audio(kind: .microphone, url: context.outputURL(for: .microphone))],
            context: context
        )
        session.startRunning()
    }

    func setMuted(_ muted: Bool) {
        isMuted = muted
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

extension MicrophoneCaptureSource: AVCaptureAudioDataOutputSampleBufferDelegate {
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard !isMuted else { return }
        writers[.microphone]?.append(sampleBuffer)
    }
}
