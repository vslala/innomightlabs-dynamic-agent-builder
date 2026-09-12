import XCTest
@testable import Aura

final class SilenceDetectorTests: XCTestCase {
    /// −40 dBFS as a linear amplitude, the default floor.
    private let quiet = 0.001
    private let loud = 0.3

    /// 100 buckets per second, matching `WaveformPeaks.defaultBucketsPerSecond`.
    private let bucket = 0.01

    private func levels(_ pattern: [(value: Double, seconds: Double)]) -> [Double] {
        pattern.flatMap { segment in
            Array(repeating: segment.value, count: Int((segment.seconds / bucket).rounded()))
        }
    }

    func testNoSilenceInContinuousSpeech() {
        let result = SilenceDetector.silences(
            levels: levels([(loud, 5)]),
            secondsPerBucket: bucket
        )
        XCTAssertTrue(result.isEmpty)
    }

    func testFindsALongPause() throws {
        // 1s speech, 2s silence, 1s speech.
        let result = SilenceDetector.silences(
            levels: levels([(loud, 1), (quiet, 2), (loud, 1)]),
            secondsPerBucket: bucket
        )

        let span = try XCTUnwrap(result.first)
        XCTAssertEqual(result.count, 1)
        // Padded by 0.1s at each end, so the cut does not clip the neighbouring words.
        XCTAssertEqual(span.start, 1.1, accuracy: 0.02)
        XCTAssertEqual(span.end, 2.9, accuracy: 0.02)
    }

    /// The property that keeps narration sounding natural: the short gaps between phrases are
    /// the rhythm of speech, and cutting them makes the result sound clipped.
    func testIgnoresShortGaps() {
        let result = SilenceDetector.silences(
            levels: levels([(loud, 1), (quiet, 0.2), (loud, 1)]),
            secondsPerBucket: bucket
        )
        XCTAssertTrue(result.isEmpty, "a 200ms gap is speech rhythm, not dead air")
    }

    func testAGapThatOnlyQualifiesBecauseOfPaddingIsNotCut() {
        // 0.36s gap: over the 0.35s minimum, but 0.2s of it is padding, leaving 0.16s.
        let result = SilenceDetector.silences(
            levels: levels([(loud, 1), (quiet, 0.36), (loud, 1)]),
            secondsPerBucket: bucket
        )
        let span = try? XCTUnwrap(result.first)
        XCTAssertEqual(result.count, 1)
        XCTAssertEqual(span?.duration ?? 0, 0.16, accuracy: 0.02)
    }

    func testFindsSeveralPausesInOrder() {
        let result = SilenceDetector.silences(
            levels: levels([(loud, 1), (quiet, 1), (loud, 1), (quiet, 1), (loud, 1)]),
            secondsPerBucket: bucket
        )
        XCTAssertEqual(result.count, 2)
        XCTAssertLessThan(result[0].start, result[1].start)
        XCTAssertLessThanOrEqual(result[0].end, result[1].start)
    }

    func testTrailingSilenceIsFound() {
        // The run has to be closed at the end of the array, not only on a transition.
        let result = SilenceDetector.silences(
            levels: levels([(loud, 1), (quiet, 2)]),
            secondsPerBucket: bucket
        )
        XCTAssertEqual(result.count, 1)
        XCTAssertEqual(result.first?.end ?? 0, 2.9, accuracy: 0.02)
    }

    func testLeadingSilenceIsFound() {
        let result = SilenceDetector.silences(
            levels: levels([(quiet, 2), (loud, 1)]),
            secondsPerBucket: bucket
        )
        XCTAssertEqual(result.count, 1)
        XCTAssertEqual(result.first?.start ?? 0, 0.1, accuracy: 0.02)
    }

    /// A muted span has no samples at all. Proposing a cut over a hole the recorder already
    /// left would be confusing, and there is nothing there to remove.
    func testUncoveredBucketsAreNotTreatedAsSilence() {
        let count = Int(3 / bucket)
        let result = SilenceDetector.silences(
            levels: Array(repeating: 0, count: count),
            secondsPerBucket: bucket,
            coverage: Array(repeating: false, count: count)
        )
        XCTAssertTrue(result.isEmpty)
    }

    func testCoverageShorterThanLevelsIsTreatedAsUncovered() {
        // Defensive: a mismatched envelope must not index out of bounds or invent silence.
        let result = SilenceDetector.silences(
            levels: Array(repeating: 0, count: 300),
            secondsPerBucket: bucket,
            coverage: [true, true]
        )
        XCTAssertTrue(result.isEmpty)
    }

    func testEmptyAndDegenerateInputs() {
        XCTAssertTrue(SilenceDetector.silences(levels: [], secondsPerBucket: bucket).isEmpty)
        XCTAssertTrue(SilenceDetector.silences(levels: [0, 0, 0], secondsPerBucket: 0).isEmpty)
    }

    func testThresholdIsRespected() {
        // Room tone at −30 dBFS is above the default −40 floor, so it is not silence.
        let roomTone = pow(10.0, -30.0 / 20)
        XCTAssertTrue(
            SilenceDetector.silences(
                levels: levels([(loud, 1), (roomTone, 2), (loud, 1)]),
                secondsPerBucket: bucket
            ).isEmpty
        )
        // Lowering the floor below it makes it silence.
        var options = SilenceDetector.Options.default
        options.floorDecibels = -20
        XCTAssertEqual(
            SilenceDetector.silences(
                levels: levels([(loud, 1), (roomTone, 2), (loud, 1)]),
                secondsPerBucket: bucket,
                options: options
            ).count,
            1
        )
    }

    func testSpansNeverOverlap() {
        let result = SilenceDetector.silences(
            levels: levels([
                (quiet, 1), (loud, 0.5), (quiet, 1), (loud, 0.5), (quiet, 1),
            ]),
            secondsPerBucket: bucket
        )
        for (earlier, later) in zip(result, result.dropFirst()) {
            XCTAssertLessThanOrEqual(earlier.end, later.start)
        }
    }
}
