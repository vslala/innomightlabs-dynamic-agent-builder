import AVFoundation
import CoreMedia

/// Mic level for the menu bar's pre-roll meter.
///
/// `FeatureFlags.isWakeWordListenerEnabled` documents a hard rule for this app: off by default
/// so that "Aura only touches the microphone during a recording". A pre-roll meter is a
/// deliberate, narrow exception to that — it must hold the microphone only while the popover
/// showing it is actually on screen. `start`/`stop` are called from `onAppear`/`onDisappear`
/// rather than from `deinit`: `deinit` is not main-actor isolated (see the note on this in
/// `ReviewViewModel`), so it cannot safely reach into this class's isolated state to tear it
/// down.
@MainActor
final class InputLevelMonitor: ObservableObject {
    /// Smoothed 0...1, for the bar.
    @Published private(set) var level: Double = 0
    /// Unsmoothed, for the numeric readout.
    @Published private(set) var dbFS: Double = InputLevelMeter.floor

    private let meter = InputLevelMeter()
    private var tap: MicrophoneLevelTap?
    private var startTask: Task<Void, Never>?

    func start(deviceID: String?) {
        stop()
        startTask = Task { [weak self] in
            guard let self else { return }
            do {
                try await CaptureAuthorization.request(.audio, denied: .microphonePermissionDenied)
            } catch {
                return
            }
            guard !Task.isCancelled else { return }

            let tap = MicrophoneLevelTap(deviceID: deviceID)
            tap.onLevel = { [weak self] rms in
                Task { @MainActor [weak self] in self?.update(rms: rms) }
            }
            guard (try? tap.start()) != nil else { return }
            self.tap = tap
        }
    }

    func stop() {
        startTask?.cancel()
        startTask = nil
        tap?.stop()
        tap = nil
        level = 0
        dbFS = InputLevelMeter.floor
    }

    private func update(rms: Double) {
        let db = meter.dbFS(rms: rms)
        level = meter.smoothed(previous: level, next: meter.normalized(dbFS: db))
        dbFS = db
    }
}

/// A dedicated, mic-only `AVCaptureSession` that reports RMS levels and writes nothing — the
/// meter's only reason to exist. Forces 16-bit mono PCM output regardless of the device's
/// native format, so the RMS computation below has one format to read rather than needing to
/// interpret whatever the hardware happens to deliver.
private final class MicrophoneLevelTap: NSObject, @unchecked Sendable {
    private let session = AVCaptureSession()
    private let output = AVCaptureAudioDataOutput()
    private let queue = DispatchQueue(label: "com.innomightlabs.aura.inputlevel")
    private let deviceID: String?

    var onLevel: (@Sendable (Double) -> Void)?

    init(deviceID: String?) {
        self.deviceID = deviceID
    }

    func start() throws {
        guard let device = Self.resolveDevice(deviceID: deviceID) else {
            throw RecordingError.writerSetupFailed("No microphone device found")
        }
        let input = try AVCaptureDeviceInput(device: device)

        output.audioSettings = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsBigEndianKey: false,
            AVNumberOfChannelsKey: 1,
            AVSampleRateKey: 44_100
        ]

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

    func stop() {
        session.stopRunning()
        session.beginConfiguration()
        session.inputs.forEach { session.removeInput($0) }
        session.outputs.forEach { session.removeOutput($0) }
        session.commitConfiguration()
    }

    private static func resolveDevice(deviceID: String?) -> AVCaptureDevice? {
        if let deviceID, let match = AVCaptureDevice(uniqueID: deviceID) {
            return match
        }
        return AVCaptureDevice.default(for: .audio)
    }
}

extension MicrophoneLevelTap: AVCaptureAudioDataOutputSampleBufferDelegate {
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard let rms = Self.rms(of: sampleBuffer) else { return }
        onLevel?(rms)
    }

    /// RMS of the buffer's 16-bit samples, normalized to `0...1` of full scale.
    private static func rms(of sampleBuffer: CMSampleBuffer) -> Double? {
        guard let blockBuffer = CMSampleBufferGetDataBuffer(sampleBuffer) else { return nil }

        var length = 0
        var dataPointer: UnsafeMutablePointer<Int8>?
        guard CMBlockBufferGetDataPointer(
            blockBuffer, atOffset: 0, lengthAtOffsetOut: nil, totalLengthOut: &length, dataPointerOut: &dataPointer
        ) == kCMBlockBufferNoErr, let dataPointer else { return nil }

        let sampleCount = length / MemoryLayout<Int16>.size
        guard sampleCount > 0 else { return nil }

        let sumOfSquares = dataPointer.withMemoryRebound(to: Int16.self, capacity: sampleCount) { samples in
            (0..<sampleCount).reduce(into: 0.0) { total, index in
                let sample = Double(samples[index])
                total += sample * sample
            }
        }
        return sqrt(sumOfSquares / Double(sampleCount)) / Double(Int16.max)
    }
}
