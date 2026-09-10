import XCTest
@testable import Aura

final class WaveformPeaksTests: XCTestCase {
    private let sampleRate: Double = 44_100
    private let bucketsPerSecond = 100

    private func accumulator(seconds: Double) -> PeakAccumulator {
        PeakAccumulator(
            bucketCount: Int(seconds * Double(bucketsPerSecond)),
            samplesPerBucket: sampleRate / Double(bucketsPerSecond),
            bucketsPerSecond: bucketsPerSecond
        )
    }

    // MARK: - Bucketing

    func testConstantSignalFillsEveryBucketWithThatValue() {
        var accumulator = self.accumulator(seconds: 1)
        accumulator.accumulate(
            Array(repeating: 0.5, count: Int(sampleRate)),
            channelCount: 1,
            firstSampleIndex: 0
        )

        let peaks = accumulator.finish()

        XCTAssertEqual(peaks.bucketCount, 100)
        XCTAssertTrue(peaks.coverage.allSatisfy { $0 })
        XCTAssertTrue(peaks.maxima.allSatisfy { abs($0 - 0.5) < 0.0001 })
        XCTAssertTrue(peaks.minima.allSatisfy { abs($0 - 0.5) < 0.0001 })
    }

    func testBucketCapturesBothExtremes() {
        var accumulator = self.accumulator(seconds: 1)
        var samples = Array(repeating: Float(0), count: Int(sampleRate))
        samples[10] = 0.9
        samples[20] = -0.7
        accumulator.accumulate(samples, channelCount: 1, firstSampleIndex: 0)

        let peaks = accumulator.finish()

        XCTAssertEqual(peaks.maxima[0], 0.9, accuracy: 0.0001)
        XCTAssertEqual(peaks.minima[0], -0.7, accuracy: 0.0001)
    }

    func testSamplesLandInTheBucketTheirIndexImplies() {
        var accumulator = self.accumulator(seconds: 2)
        // One sample half a second in, which is bucket 50 at 100 buckets/second.
        accumulator.accumulate([0.8], channelCount: 1, firstSampleIndex: Int(sampleRate / 2))

        let peaks = accumulator.finish()

        XCTAssertTrue(peaks.coverage[50])
        XCTAssertEqual(peaks.maxima[50], 0.8, accuracy: 0.0001)
        XCTAssertFalse(peaks.coverage[49])
        XCTAssertFalse(peaks.coverage[51])
    }

    func testSamplesArePlacedByTheGivenIndexNotByArrivalOrder() {
        // The muted-span case: the reader jumps the presentation timestamp across an empty
        // edit rather than emitting silence, so a buffer arriving second can belong a long
        // way further along the timeline. Counting samples instead would drag it back to the
        // start and smear the whole waveform earlier.
        var accumulator = self.accumulator(seconds: 3)
        accumulator.accumulate(Array(repeating: 0.4, count: 4410), channelCount: 1, firstSampleIndex: 0)
        accumulator.accumulate(
            Array(repeating: 0.6, count: 4410),
            channelCount: 1,
            firstSampleIndex: Int(sampleRate * 2)
        )

        let peaks = accumulator.finish()

        XCTAssertTrue(peaks.coverage[0..<10].allSatisfy { $0 }, "First buffer covers 0-0.1s")
        XCTAssertTrue(peaks.coverage[10..<200].allSatisfy { !$0 }, "The muted span stays uncovered")
        XCTAssertTrue(peaks.coverage[200..<210].allSatisfy { $0 }, "Second buffer lands at 2s")
        XCTAssertEqual(peaks.maxima[200], 0.6, accuracy: 0.0001)
    }

    func testUncoveredBucketsAreDistinguishableFromSilentOnes() {
        var accumulator = self.accumulator(seconds: 1)
        // Genuine digital silence in the first tenth of a second.
        accumulator.accumulate(Array(repeating: 0, count: 4410), channelCount: 1, firstSampleIndex: 0)

        let peaks = accumulator.finish()

        XCTAssertTrue(peaks.coverage[0], "Silence that was recorded is covered")
        XCTAssertEqual(peaks.maxima[0], 0)
        XCTAssertFalse(peaks.coverage[99], "Audio that was never written is not covered")
    }

    func testStereoInterleavedSamplesAreBothConsidered() {
        var accumulator = self.accumulator(seconds: 1)
        accumulator.accumulate([0.1, 0.9, -0.8, 0.2], channelCount: 2, firstSampleIndex: 0)

        let peaks = accumulator.finish()

        XCTAssertEqual(peaks.maxima[0], 0.9, accuracy: 0.0001)
        XCTAssertEqual(peaks.minima[0], -0.8, accuracy: 0.0001)
    }

    func testSamplesOutsideTheBucketRangeAreIgnoredRatherThanCrashing() {
        var accumulator = self.accumulator(seconds: 1)
        accumulator.accumulate([0.5], channelCount: 1, firstSampleIndex: Int(sampleRate * 99))
        accumulator.accumulate([0.5], channelCount: 1, firstSampleIndex: -1000)

        XCTAssertTrue(accumulator.finish().coverage.allSatisfy { !$0 })
    }

    func testNonFiniteSamplesAreSkipped() {
        var accumulator = self.accumulator(seconds: 1)
        accumulator.accumulate([.nan, .infinity, 0.3], channelCount: 1, firstSampleIndex: 0)

        let peaks = accumulator.finish()

        XCTAssertEqual(peaks.maxima[0], 0.3, accuracy: 0.0001)
        XCTAssertTrue(peaks.maxima.allSatisfy(\.isFinite))
    }

    func testFractionalSamplesPerBucketDoesNotDriftOverALongRecording() {
        // 44100/128 is not an integer; truncating it would drift visibly over 30 minutes.
        var accumulator = PeakAccumulator(
            bucketCount: 128 * 60,
            samplesPerBucket: sampleRate / 128,
            bucketsPerSecond: 128
        )
        // A single sample at the 59-second mark must land in the final second's buckets.
        accumulator.accumulate([0.9], channelCount: 1, firstSampleIndex: Int(sampleRate * 59))

        let peaks = accumulator.finish()
        let covered = peaks.coverage.firstIndex(of: true)

        XCTAssertEqual(covered, 128 * 59)
    }

    // MARK: - Reduction for zooming out

    func testReductionTakesMinOfMinsAndMaxOfMaxes() {
        let peaks = WaveformPeaks(
            bucketsPerSecond: 4,
            minima: [-0.1, -0.9, -0.2, -0.3],
            maxima: [0.4, 0.2, 0.8, 0.1],
            coverage: [true, true, true, true]
        )

        let reduced = peaks.reduced(toAtMost: 2)

        XCTAssertEqual(reduced.minima, [-0.9, -0.3])
        XCTAssertEqual(reduced.maxima, [0.4, 0.8])
    }

    func testReductionKeepsABucketCoveredIfAnySourceBucketWas() {
        let peaks = WaveformPeaks(
            bucketsPerSecond: 4,
            minima: [0, 0, 0, 0],
            maxima: [0, 0.5, 0, 0],
            coverage: [false, true, false, false]
        )

        let reduced = peaks.reduced(toAtMost: 2)

        XCTAssertEqual(reduced.coverage, [true, false])
    }

    func testReductionToMoreBucketsThanExistIsANoOp() {
        let peaks = WaveformPeaks(bucketsPerSecond: 4, minima: [0], maxima: [1], coverage: [true])
        XCTAssertEqual(peaks.reduced(toAtMost: 100), peaks)
    }

    func testEmptyPeaksReduceWithoutCrashing() {
        XCTAssertEqual(WaveformPeaks.empty.reduced(toAtMost: 10), .empty)
    }

    func testDurationFollowsBucketCountAndRate() {
        let peaks = WaveformPeaks(
            bucketsPerSecond: 100,
            minima: Array(repeating: 0, count: 250),
            maxima: Array(repeating: 0, count: 250),
            coverage: Array(repeating: true, count: 250)
        )

        XCTAssertEqual(peaks.duration, 2.5)
    }
}
