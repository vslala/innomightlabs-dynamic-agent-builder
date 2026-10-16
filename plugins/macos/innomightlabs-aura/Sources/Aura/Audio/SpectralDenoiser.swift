import Accelerate
import Foundation

/// Removes steady background noise (fans, hiss, room tone) from one channel of speech.
///
/// Pure and streaming: samples go in, the same number come out, and nothing here knows about
/// files, AVFoundation or the review window. The renderer feeds it from a file; a live monitor
/// could feed it from a microphone tap.
///
/// The method is spectral gating. Each frame is windowed and transformed, every frequency bin
/// is attenuated by how far its power sits above that bin's *tracked noise floor*, and the
/// frames are overlapped back together. The floor is learned as the audio plays — it falls to
/// any quieter reading at once and creeps upward slowly — so there is no separate noise-profile
/// pass and the recording never has to be held in memory.
///
/// Not `Sendable`: it owns an `FFT` plan. Create one per channel, per render.
struct SpectralDenoiser {
    struct Options: Equatable, Sendable {
        /// How far to push down what is judged to be noise, in dB. Deeper than ~18 dB starts
        /// to sound underwater, because the residue is gated in and out.
        var reductionDecibels: Double = 14
        /// How fast the noise floor may rise while the signal stays above it, as a factor per
        /// second. Slow enough that a held vowel is not learned as noise, fast enough to follow
        /// a fan changing speed.
        var floorRisePerSecond: Double = 2

        static let `default` = Options()
    }

    private static let frameSize = 1024
    private static let hopSize = frameSize / 4
    private static let binCount = frameSize / 2
    /// Samples a frame's neighbours still owe the start of the stream. Priming with this much
    /// silence, and dropping the same amount of output, makes every real sample receive the
    /// full overlap.
    private static let latency = frameSize - hopSize
    /// Squared and summed over a 4x overlap, a Hann window adds up to 2.
    private static let overlapGain: Float = 2
    /// The tracked floor is a *minimum* of a fluctuating power, which sits below its mean. This
    /// brings it back up to the level noise actually averages.
    private static let floorBias: Float = 3.5

    private let options: Options
    private let fft: vDSP.FFT<DSPSplitComplex>
    private let window: [Float]
    private let risePerFrame: Float
    private let reductionGain: Float

    private var pending = [Float](repeating: 0, count: SpectralDenoiser.latency)
    private var overlap = [Float](repeating: 0, count: SpectralDenoiser.frameSize)
    private var smoothedPower = [Float](repeating: 0, count: SpectralDenoiser.binCount)
    private var noiseFloor = [Float](repeating: 0, count: SpectralDenoiser.binCount)
    private var smoothedGain = [Float](repeating: 1, count: SpectralDenoiser.binCount)
    private var toDrop = SpectralDenoiser.latency
    private var samplesIn = 0
    private var samplesOut = 0

    init(sampleRate: Double, options: Options = .default) {
        self.options = options
        let log2n = vDSP_Length(Self.frameSize.trailingZeroBitCount)
        // Only fails for a size that is not a power of two, which `frameSize` always is.
        fft = vDSP.FFT(log2n: log2n, radix: .radix2, ofType: DSPSplitComplex.self)!
        // Square-root Hann on analysis and synthesis: the two multiply to Hann.
        window = (0..<Self.frameSize).map {
            Float(sqrt(0.5 - 0.5 * cos(2 * Double.pi * Double($0) / Double(Self.frameSize))))
        }
        risePerFrame = Float(pow(options.floorRisePerSecond, Double(Self.hopSize) / sampleRate))
        reductionGain = Float(pow(10, -options.reductionDecibels / 20))
    }

    /// Feeds more audio and returns whatever is now final: the output trails the input by
    /// `latency` samples until `finish()`.
    mutating func process(_ samples: [Float]) -> [Float] {
        samplesIn += samples.count
        pending.append(contentsOf: samples)
        return drain()
    }

    /// Flushes the tail, so that across all calls exactly as many samples come out as went in.
    mutating func finish() -> [Float] {
        pending.append(contentsOf: [Float](repeating: 0, count: Self.frameSize))
        return drain()
    }

    // MARK: - Framing

    private mutating func drain() -> [Float] {
        var output: [Float] = []
        var start = 0

        while pending.count - start >= Self.frameSize {
            let frame = Array(pending[start..<start + Self.frameSize])
            start += Self.hopSize

            vDSP.add(overlap, synthesize(frame), result: &overlap)
            output.append(contentsOf: overlap[0..<Self.hopSize])
            overlap.removeFirst(Self.hopSize)
            overlap.append(contentsOf: [Float](repeating: 0, count: Self.hopSize))
        }
        pending.removeFirst(start)

        let primed = min(toDrop, output.count)
        toDrop -= primed
        output.removeFirst(primed)

        // The zero padding in `finish` produces output beyond the real input.
        let room = max(0, samplesIn - samplesOut)
        if output.count > room { output.removeLast(output.count - room) }
        samplesOut += output.count
        return output
    }

    // MARK: - One frame

    private mutating func synthesize(_ frame: [Float]) -> [Float] {
        let half = Self.binCount
        let windowed = vDSP.multiply(frame, window)
        var real = [Float](repeating: 0, count: half)
        var imaginary = [Float](repeating: 0, count: half)
        var output = [Float](repeating: 0, count: Self.frameSize)

        real.withUnsafeMutableBufferPointer { realPointer in
            imaginary.withUnsafeMutableBufferPointer { imaginaryPointer in
                var split = DSPSplitComplex(realp: realPointer.baseAddress!, imagp: imaginaryPointer.baseAddress!)
                windowed.withUnsafeBufferPointer { input in
                    input.baseAddress!.withMemoryRebound(to: DSPComplex.self, capacity: half) {
                        vDSP_ctoz($0, 2, &split, 1, vDSP_Length(half))
                    }
                }
                fft.forward(input: split, output: &split)
                applyGain(to: &split)
                fft.inverse(input: split, output: &split)
                output.withUnsafeMutableBufferPointer { out in
                    out.baseAddress!.withMemoryRebound(to: DSPComplex.self, capacity: half) {
                        vDSP_ztoc(&split, 1, $0, 2, vDSP_Length(half))
                    }
                }
            }
        }

        // vDSP's real transform scales a forward-inverse round trip by 2n; the overlap-add of
        // squared windows adds `overlapGain` on top.
        var scale = 1 / (Float(2 * Self.frameSize) * Self.overlapGain)
        vDSP_vsmul(output, 1, &scale, &output, 1, vDSP_Length(Self.frameSize))
        return vDSP.multiply(output, window)
    }

    /// The whole denoising decision: one gain per frequency bin.
    private mutating func applyGain(to split: inout DSPSplitComplex) {
        // vDSP packs DC into `realp[0]` and Nyquist into `imagp[0]`. Neither carries speech, so
        // both are simply pushed down rather than tracked.
        split.realp[0] *= reductionGain
        split.imagp[0] *= reductionGain

        for bin in 1..<Self.binCount {
            let re = split.realp[bin]
            let im = split.imagp[bin]
            let power = re * re + im * im

            // Smoothing the power before taking its minimum keeps one quiet frame from being
            // mistaken for the noise level.
            // A bin that has only ever seen digital silence (the zero priming, or a muted gap)
            // has nothing to learn from yet, and a floor of exactly zero could never rise.
            let isLearning = noiseFloor[bin] == 0
            smoothedPower[bin] = isLearning ? power : 0.8 * smoothedPower[bin] + 0.2 * power
            noiseFloor[bin] = isLearning
                ? smoothedPower[bin]
                : min(smoothedPower[bin], noiseFloor[bin] * risePerFrame)

            // Wiener-style: keep the share of this bin's power that is above the floor.
            let noise = noiseFloor[bin] * Self.floorBias
            let wanted = power > noise ? max(reductionGain, 1 - noise / power) : reductionGain

            // Fall quickly, recover slowly: hides the flicker ("musical noise") a bin-by-bin
            // gate makes as it opens and closes.
            let smoothing: Float = wanted < smoothedGain[bin] ? 0.4 : 0.85
            smoothedGain[bin] = smoothing * smoothedGain[bin] + (1 - smoothing) * wanted

            split.realp[bin] = re * smoothedGain[bin]
            split.imagp[bin] = im * smoothedGain[bin]
        }
    }
}
