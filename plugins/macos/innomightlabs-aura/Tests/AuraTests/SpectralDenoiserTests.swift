import XCTest
@testable import Aura

final class SpectralDenoiserTests: XCTestCase {
    private let sampleRate = 48_000.0

    func testReturnsExactlyAsManySamplesAsItWasGiven() {
        for count in [0, 1, 255, 1024, 5_000, 48_000] {
            var denoiser = SpectralDenoiser(sampleRate: sampleRate)
            let output = denoiser.process(noise(count, amplitude: 0.1)) + denoiser.finish()
            XCTAssertEqual(output.count, count, "length changed for \(count) samples")
        }
    }

    func testChunkSizeDoesNotChangeTheResult() {
        let input = noise(20_000, amplitude: 0.1)

        var whole = SpectralDenoiser(sampleRate: sampleRate)
        let expected = whole.process(input) + whole.finish()

        var chunked = SpectralDenoiser(sampleRate: sampleRate)
        var actual: [Float] = []
        var offset = 0
        for size in [1, 7, 300, 4_096, 99].cycled(until: input.count) {
            let end = min(offset + size, input.count)
            actual += chunked.process(Array(input[offset..<end]))
            offset = end
        }
        actual += chunked.finish()

        XCTAssertEqual(actual.count, expected.count)
        XCTAssertEqual(maxDifference(actual, expected), 0, accuracy: 1e-5)
    }

    func testWithNoReductionAudioPassesThroughUnchangedAndInStep() {
        // Pins the transform's scaling and the latency compensation: a wrong gain or a
        // misaligned start would show up here and nowhere subtler.
        let input = tone(frequency: 440, amplitude: 0.5, count: 12_000)
        var denoiser = SpectralDenoiser(sampleRate: sampleRate, options: .init(reductionDecibels: 0))
        let output = denoiser.process(input) + denoiser.finish()

        XCTAssertEqual(maxDifference(output, input), 0, accuracy: 1e-3)
    }

    func testSteadyNoiseIsReducedSubstantially() {
        let input = noise(sampleRate * 4, amplitude: 0.02)
        var denoiser = SpectralDenoiser(sampleRate: sampleRate)
        let output = denoiser.process(input) + denoiser.finish()

        // Judged after the floor has had time to settle.
        let reduction = decibels(rms(tail(input)) / rms(tail(output)))
        XCTAssertGreaterThan(reduction, 8)
    }

    func testSpeechLikeBurstsSurviveWhileTheGapsBetweenThemAreCleaned() {
        // A steady tone is indistinguishable from steady noise to any floor tracker, so the
        // stand-in for speech is a tone that stops and starts, as speech does.
        let rate = Int(sampleRate)
        let burst = tone(frequency: 1_000, amplitude: 0.3, count: rate * 5)
            .enumerated().map { ($0 / (rate * 3 / 10)) % 2 == 0 ? $1 : 0 }
        let hiss = noise(burst.count, amplitude: 0.02)
        let noisy = zip(burst, hiss).map { $0 + $1 }

        var denoiser = SpectralDenoiser(sampleRate: sampleRate)
        let output = denoiser.process(noisy) + denoiser.finish()

        // Judged on the last two seconds, after the floor has settled. Edges of each burst are
        // skipped, where the gain is still opening.
        let settled = (rate * 3)..<(rate * 5)
        let spoken = settled.filter { index in
            let inBurst = (index / (rate * 3 / 10)) % 2 == 0
            let intoBurst = index % (rate * 3 / 10)
            return inBurst && intoBurst > rate / 20 && intoBurst < rate * 3 / 10 - rate / 20
        }
        let gaps = settled.filter { ($0 / (rate * 3 / 10)) % 2 == 1 }

        let kept = decibels(rms(spoken.map { output[$0] }) / rms(spoken.map { burst[$0] }))
        XCTAssertEqual(kept, 0, accuracy: 2, "the voiced part was changed in level")

        let cleaned = decibels(rms(gaps.map { hiss[$0] }) / rms(gaps.map { output[$0] }))
        XCTAssertGreaterThan(cleaned, 8, "the hiss between bursts was not reduced")
    }

    func testSilenceStaysSilentAndDoesNotPoisonTheFloor() {
        var denoiser = SpectralDenoiser(sampleRate: sampleRate)
        let silence = denoiser.process([Float](repeating: 0, count: 10_000))
        XCTAssertEqual(silence.max() ?? 0, 0, accuracy: 1e-9)

        // Noise arriving after digital silence must still be learned and reduced.
        let hiss = noise(sampleRate * 3, amplitude: 0.02)
        let output = denoiser.process(hiss) + denoiser.finish()
        XCTAssertGreaterThan(decibels(rms(tail(hiss)) / rms(tail(output))), 8)
    }

    // MARK: - Signals

    /// Deterministic, so a failure reproduces.
    private func noise(_ count: Double, amplitude: Float) -> [Float] { noise(Int(count), amplitude: amplitude) }

    private func noise(_ count: Int, amplitude: Float) -> [Float] {
        var state: UInt64 = 0x9E37_79B9_7F4A_7C15
        return (0..<count).map { _ in
            state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
            return (Float(state >> 40) / Float(1 << 24) * 2 - 1) * amplitude
        }
    }

    private func tone(frequency: Double, amplitude: Float, count: Int) -> [Float] {
        (0..<count).map { amplitude * Float(sin(2 * Double.pi * frequency * Double($0) / sampleRate)) }
    }

    private func rms(_ samples: [Float]) -> Float {
        guard !samples.isEmpty else { return 0 }
        return (samples.map { $0 * $0 }.reduce(0, +) / Float(samples.count)).squareRoot()
    }

    private func decibels(_ ratio: Float) -> Float { 20 * log10(ratio) }

    private func tail(_ samples: [Float]) -> [Float] {
        Array(samples.suffix(Int(sampleRate)))
    }

    private func maxDifference(_ a: [Float], _ b: [Float]) -> Float {
        zip(a, b).map { abs($0 - $1) }.max() ?? 0
    }
}

private extension Array where Element == Int {
    /// Repeats the sizes until they have covered `total` samples.
    func cycled(until total: Int) -> [Int] {
        var sizes: [Int] = []
        var covered = 0
        while covered < total {
            let next = self[sizes.count % count]
            sizes.append(next)
            covered += next
        }
        return sizes
    }
}
