import AVFoundation

/// Owns the single always-on `AVAudioEngine` mic tap for voice control. Runs the
/// wake-word pipeline on every chunk and exposes the same resampled (16kHz mono,
/// standard `[-1,1]` range) buffers via `onRawBuffer` so `CommandCapture` can consume
/// the identical audio stream without installing a second competing tap.
final class WakeWordListener {
    var onDetection: (() -> Void)?
    var onRawBuffer: ((AVAudioPCMBuffer) -> Void)?
    var onScore: ((Float) -> Void)?

    private let engine = AVAudioEngine()
    private let pipeline: WakeWordFeaturePipeline
    private let threshold: Float
    private let cooldown: TimeInterval

    private var resampler: AudioResampler?
    private var sampleAccumulator: [Float] = []
    private var cooldownUntil: Date = .distantPast

    init(pipeline: WakeWordFeaturePipeline, threshold: Float = 0.5, cooldown: TimeInterval = 2.0) {
        self.pipeline = pipeline
        self.threshold = threshold
        self.cooldown = cooldown
    }

    func start() throws {
        let input = engine.inputNode
        let inputFormat = input.inputFormat(forBus: 0)
        guard let resampler = AudioResampler(inputFormat: inputFormat) else {
            throw VoiceError.modelLoadFailed("Could not create a 16kHz mono resampler for input format \(inputFormat)")
        }
        self.resampler = resampler

        input.installTap(onBus: 0, bufferSize: 1024, format: inputFormat) { [weak self] buffer, _ in
            self?.handle(buffer)
        }
        engine.prepare()
        try engine.start()
    }

    func stop() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
    }

    private func handle(_ buffer: AVAudioPCMBuffer) {
        guard let resampler, let resampled = resampler.resample(buffer) else { return }
        onRawBuffer?(resampled)
        feedPipeline(resampled)
    }

    private func feedPipeline(_ buffer: AVAudioPCMBuffer) {
        guard let channelData = buffer.floatChannelData else { return }
        let frameCount = Int(buffer.frameLength)
        for index in 0..<frameCount {
            sampleAccumulator.append(channelData[0][index] * 32_768.0)
        }

        while sampleAccumulator.count >= Melspectrogram.inputChunkSize {
            let chunk = Array(sampleAccumulator.prefix(Melspectrogram.inputChunkSize))
            sampleAccumulator.removeFirst(Melspectrogram.inputChunkSize)

            guard let score = try? pipeline.process(samples: chunk) else { continue }
            onScore?(score)
            if score > threshold, Date() > cooldownUntil {
                cooldownUntil = Date().addingTimeInterval(cooldown)
                onDetection?()
            }
        }
    }
}
