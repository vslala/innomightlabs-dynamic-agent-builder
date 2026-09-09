import Accelerate
import Foundation

/// Hand-rolled Swift/Accelerate port of openWakeWord's `melspectrogram.onnx`.
///
/// This one stage could not be converted to CoreML — two independent toolchains
/// (onnx2torch->CoreML, onnx2tf->TensorFlow->CoreML) both hit real bugs on its custom
/// STFT implementation. Ported directly from the ONNX graph instead: a "Conv1D-as-STFT"
/// trick (512-sample window, 160-sample hop) producing real/imag STFT bins via matrix
/// multiply against precomputed weights, a 257->32 mel filterbank projection, log
/// magnitude, and a dynamic top-80dB clip relative to this chunk's own peak. See
/// docs/LLD-aura-phase2-voice-control.md for the full derivation.
final class Melspectrogram {
    static let nFFT = 512
    static let hopLength = 160
    static let melBins = 32
    static let fftBins = 257

    /// The chunk size callers should accumulate before calling `process` — 1280 raw
    /// samples (80ms @ 16kHz), yielding exactly 5 frames: `(1280-512)/160+1 = 5`.
    static let inputChunkSize = 1280

    private let convReal: [Float] // fftBins x nFFT, row-major
    private let convImag: [Float] // fftBins x nFFT, row-major
    private let melW: [Float]     // fftBins x melBins, row-major

    init(resourcesURL: URL) throws {
        convReal = try Self.loadFloats(resourcesURL.appendingPathComponent("melspec_conv_real_257x512.bin"), count: Self.fftBins * Self.nFFT)
        convImag = try Self.loadFloats(resourcesURL.appendingPathComponent("melspec_conv_imag_257x512.bin"), count: Self.fftBins * Self.nFFT)
        melW = try Self.loadFloats(resourcesURL.appendingPathComponent("melspec_mel_w_257x32.bin"), count: Self.fftBins * Self.melBins)
    }

    /// `samples` must be exactly 1280 raw (int16-range, unnormalized) float32 samples
    /// (80ms @ 16kHz). Returns `frameCount` (always 5 for 1280 samples) row-major mel
    /// frames, each `melBins` wide.
    func process(samples: [Float]) -> (frameCount: Int, values: [Float]) {
        precondition(samples.count >= Self.nFFT, "need at least \(Self.nFFT) samples")

        let frameCount = (samples.count - Self.nFFT) / Self.hopLength + 1
        var output = [Float](repeating: 0, count: frameCount * Self.melBins)

        for frame in 0..<frameCount {
            let start = frame * Self.hopLength
            let frameSamples = Array(samples[start..<(start + Self.nFFT)])

            var real = [Float](repeating: 0, count: Self.fftBins)
            var imag = [Float](repeating: 0, count: Self.fftBins)
            vDSP_mmul(convReal, 1, frameSamples, 1, &real, 1, vDSP_Length(Self.fftBins), 1, vDSP_Length(Self.nFFT))
            vDSP_mmul(convImag, 1, frameSamples, 1, &imag, 1, vDSP_Length(Self.fftBins), 1, vDSP_Length(Self.nFFT))

            var power = [Float](repeating: 0, count: Self.fftBins)
            for k in 0..<Self.fftBins {
                power[k] = real[k] * real[k] + imag[k] * imag[k]
            }

            var mel = [Float](repeating: 0, count: Self.melBins)
            vDSP_mmul(power, 1, melW, 1, &mel, 1, 1, vDSP_Length(Self.melBins), vDSP_Length(Self.fftBins))

            for m in 0..<Self.melBins {
                output[frame * Self.melBins + m] = 10 * log10f(max(mel[m], 1e-10))
            }
        }

        let maxDb = output.max() ?? 0
        let floor = maxDb - 80
        for i in output.indices {
            output[i] = max(output[i], floor) / 10 + 2
        }

        return (frameCount, output)
    }

    private static func loadFloats(_ url: URL, count: Int) throws -> [Float] {
        let data = try Data(contentsOf: url)
        precondition(data.count == count * MemoryLayout<Float>.size, "\(url.lastPathComponent): expected \(count) floats, got \(data.count) bytes")
        return data.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
    }
}
