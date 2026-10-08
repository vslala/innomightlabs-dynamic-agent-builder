import AVFoundation
import CoreMedia

/// Owns a dedicated, mic-only `AVCaptureSession` for `microphone.m4a`.
final class MicrophoneCaptureSource: NSObject, CaptureSource, @unchecked Sendable {
    /// The one format this source ever hands its writer.
    ///
    /// Left unset, `AVCaptureAudioDataOutput` passes through whatever the audio system is
    /// producing, and that can change a few milliseconds into a take — the Fifine went from
    /// 16-bit integer to 32-bit float non-interleaved at 11 ms in `20261008-023721-ea5b`.
    /// `AVAssetWriter` keeps decoding with the first buffer's format, so every buffer after
    /// the switch is misread and the whole track becomes loud noise, with no error from the
    /// writer. With settings pinned, the output converts internally and never changes.
    /// Float, so a hot signal keeps its headroom through the conversion; mono, because a
    /// narration mic is one voice.
    static var captureAudioSettings: [String: Any] {
        [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVLinearPCMBitDepthKey: 32,
            AVLinearPCMIsFloatKey: true,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsNonInterleaved: false,
            AVNumberOfChannelsKey: 1,
            AVSampleRateKey: 48_000
        ]
    }

    private let session = AVCaptureSession()
    private let output = AVCaptureAudioDataOutput()
    private let queue = DispatchQueue(label: "com.innomightlabs.aura.microphone")

    private let deviceID: String?

    let kinds: [TrackKind] = [.microphone]
    private(set) var writers: [TrackKind: TrackWriter] = [:]
    var onFailure: (@Sendable (Error) -> Void)?
    var onNotice: (@Sendable (CaptureSourceNotice) -> Void)?

    /// Set in `prepare`, read on the capture queue once the session is running.
    private var deviceName = "Unknown microphone"

    /// Capture-queue state only, reset in `start`: the last format reported, so a mid-take
    /// change is logged; the guard keeping the writer on one format; and the monitor
    /// watching for a broken signal.
    private var lastFormat: String?
    private var formatGuard = WriterFormatGuard()
    private var signalMonitor = MicrophoneSignalMonitor()

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
        deviceName = device.localizedName

        session.beginConfiguration()
        if session.canAddInput(input) {
            session.addInput(input)
        }
        output.audioSettings = Self.captureAudioSettings
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
        queue.sync {
            lastFormat = nil
            formatGuard = WriterFormatGuard()
            signalMonitor = MicrophoneSignalMonitor()
        }
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
        let time = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        let format = CMSampleBufferGetFormatDescription(sampleBuffer)
            .flatMap { CMAudioFormatDescriptionGetStreamBasicDescription($0)?.pointee }
            .map(AudioFormatSummary.describe)

        if let format, format != lastFormat {
            lastFormat = format
            onNotice?(.inputFormat(kind: .microphone, device: deviceName, format: format, at: time))
        }

        switch formatGuard.admit(format) {
        case .write:
            writers[.microphone]?.append(sampleBuffer)
        case .drop(let isFirstMismatch):
            // A gap is recoverable; a file the writer has misread from here on is not.
            if isFirstMismatch, let established = formatGuard.established {
                let reason = "format changed from \(established) to \(format ?? "unknown")"
                onNotice?(.signalSuspect(kind: .microphone, device: deviceName, reason: reason, at: time))
            }
            return
        }

        // After the append, so watching the signal can never delay a buffer reaching the
        // writer; it only reads the samples.
        if let chunk = SignalChunk(sampleBuffer), let problem = signalMonitor.ingest(chunk) {
            onNotice?(.signalSuspect(kind: .microphone, device: deviceName, reason: problem.summary, at: time))
        }
    }
}

/// Keeps a writer on the format its file started with.
///
/// `AVAssetWriterInput` accepts a buffer in a new format without complaint and then decodes
/// it with the old one, which turns the rest of the track into noise. The pinned
/// `captureAudioSettings` should mean the format never changes; this is what makes sure that
/// if it ever does, the damage is a gap rather than the whole recording.
struct WriterFormatGuard {
    enum Decision: Equatable {
        case write
        /// `isFirstMismatch` is true only for the first dropped buffer, so the change is
        /// reported once rather than for every buffer that follows.
        case drop(isFirstMismatch: Bool)
    }

    private(set) var established: String?
    private var hasReportedMismatch = false

    mutating func admit(_ format: String?) -> Decision {
        // An unreadable description is not evidence of a change; let the writer have it.
        guard let format else { return .write }
        guard let established else {
            self.established = format
            return .write
        }
        if format == established { return .write }

        defer { hasReportedMismatch = true }
        return .drop(isFirstMismatch: !hasReportedMismatch)
    }
}
