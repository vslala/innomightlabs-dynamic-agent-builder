import XCTest
@testable import Aura

final class TimeStretcherTests: XCTestCase {
    private let rate = 24_000.0

    private func tone(_ hertz: Double, seconds: Double, amplitude: Float = 0.5) -> [Float] {
        (0..<Int(rate * seconds)).map { amplitude * Float(sin(2 * Double.pi * hertz * Double($0) / rate)) }
    }

    /// Upward zero crossings per second — the pitch of a clean tone.
    private func frequency(_ samples: [Float]) -> Double {
        var crossings = 0
        for index in 1..<samples.count where samples[index - 1] <= 0 && samples[index] > 0 { crossings += 1 }
        return Double(crossings) / (Double(samples.count) / rate)
    }

    private func rms(_ samples: [Float]) -> Float {
        (samples.map { $0 * $0 }.reduce(0, +) / Float(samples.count)).squareRoot()
    }

    func testFasterTempoShortensTheClipByThatFactor() {
        let input = tone(200, seconds: 3)
        let output = TimeStretcher.stretch(input, tempo: 1.1)

        XCTAssertEqual(Double(output.count) / Double(input.count), 1 / 1.1, accuracy: 0.01)
    }

    func testSlowerTempoLengthensIt() {
        let input = tone(200, seconds: 3)
        let output = TimeStretcher.stretch(input, tempo: 0.9)

        XCTAssertEqual(Double(output.count) / Double(input.count), 1 / 0.9, accuracy: 0.01)
    }

    func testPitchIsUnchanged() {
        let input = tone(220, seconds: 3)
        for tempo in [0.85, 1.15] {
            let output = TimeStretcher.stretch(input, tempo: tempo)
            XCTAssertEqual(frequency(output), 220, accuracy: 6, "pitch moved at tempo \(tempo)")
        }
    }

    func testLoudnessIsKept() {
        let input = tone(220, seconds: 3)
        let output = TimeStretcher.stretch(input, tempo: 1.15)

        XCTAssertEqual(rms(output) / rms(input), 1, accuracy: 0.08)
    }

    func testUnitTempoAndTinyInputsPassThroughUntouched() {
        let input = tone(200, seconds: 1)
        XCTAssertEqual(TimeStretcher.stretch(input, tempo: 1), input)
        XCTAssertEqual(TimeStretcher.stretch([0.1, 0.2], tempo: 1.2), [0.1, 0.2])
        XCTAssertEqual(TimeStretcher.stretch(input, tempo: 0), input)
        XCTAssertEqual(TimeStretcher.stretch(input, tempo: .nan), input)
    }
}
