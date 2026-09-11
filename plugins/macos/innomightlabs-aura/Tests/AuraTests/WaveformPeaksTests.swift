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

    // MARK: - RMS

    func testRMSIsTheQuadraticMeanOfTheBucket() {
        var accumulator = self.accumulator(seconds: 1)
        // Half at 0.8, half at 0: RMS = sqrt((0.64 + 0) / 2) = 0.5657
        var samples = Array(repeating: Float(0.8), count: 220)
        samples += Array(repeating: Float(0), count: 221)
        accumulator.accumulate(samples, channelCount: 1, firstSampleIndex: 0)

        let peaks = accumulator.finish()

        XCTAssertEqual(peaks.rms[0], 0.5657, accuracy: 0.005)
        XCTAssertEqual(peaks.maxima[0], 0.8, accuracy: 0.0001)
    }

    func testRMSIsWellBelowThePeakForSpeechLikeContent() {
        // Why the RMS band exists: the peak says almost nothing about where the body of the
        // audio is. A single spike in an otherwise quiet bucket barely moves the RMS.
        var accumulator = self.accumulator(seconds: 1)
        var samples = Array(repeating: Float(0.01), count: 441)
        samples[10] = 0.9
        accumulator.accumulate(samples, channelCount: 1, firstSampleIndex: 0)

        let peaks = accumulator.finish()

        XCTAssertEqual(peaks.maxima[0], 0.9, accuracy: 0.0001)
        XCTAssertLessThan(peaks.rms[0], 0.1)
    }

    func testUncoveredBucketsHaveZeroRMS() {
        var accumulator = self.accumulator(seconds: 1)
        accumulator.accumulate([0.5], channelCount: 1, firstSampleIndex: 0)

        XCTAssertEqual(accumulator.finish().rms[99], 0)
    }

    func testReductionCombinesRMSQuadratically() {
        // Averaging RMS values directly would understate loudness.
        let peaks = WaveformPeaks(
            bucketsPerSecond: 4,
            minima: [0, 0, 0, 0],
            maxima: [1, 1, 1, 1],
            rms: [0.6, 0.8, 0, 0],
            coverage: [true, true, true, true]
        )

        let reduced = peaks.reduced(toAtMost: 2)

        // sqrt((0.36 + 0.64) / 2) = 0.7071, not (0.6 + 0.8) / 2 = 0.7
        XCTAssertEqual(reduced.rms[0], 0.7071, accuracy: 0.001)
    }

    // MARK: - Vertical scale
    //
    // Measured on a real recording: peak 0.35 (-9 dBFS) but a median 10ms bucket of 0.0022.
    // These tests pin why a linear axis is unusable for speech and dB is the default.

    func testLinearScaleIsPassthrough() {
        XCTAssertEqual(WaveformScale.linear.fraction(0.5), 0.5, accuracy: 0.0001)
        XCTAssertEqual(WaveformScale.linear.fraction(-0.25), -0.25, accuracy: 0.0001)
    }

    func testLinearScaleRendersATypicalSpeechBucketAsSubPixel() {
        // 0.22% of half-height — a flat line, which is exactly what was reported.
        XCTAssertLessThan(WaveformScale.linear.fraction(0.0022), 0.003)
    }

    func testDecibelScaleLiftsThatSameBucketIntoView() {
        let fraction = WaveformScale.decibel.fraction(0.0022)

        XCTAssertGreaterThan(fraction, 0.08, "a median speech bucket should be visible")
        XCTAssertLessThan(fraction, 0.25, "but not so lifted that everything looks loud")
    }

    func testDecibelScaleKeepsPeaksNearTheTopWithoutClipping() {
        XCTAssertEqual(WaveformScale.decibel.fraction(1.0), 1.0, accuracy: 0.0001)
        let realPeak = WaveformScale.decibel.fraction(0.35)
        XCTAssertGreaterThan(realPeak, 0.8)
        XCTAssertLessThanOrEqual(realPeak, 1.0)
    }

    func testDecibelScalePreservesOrdering() {
        // Louder must always draw taller, or the shape misleads.
        let values: [Float] = [0.0001, 0.001, 0.01, 0.05, 0.2, 0.5, 1.0]
        let fractions = values.map { WaveformScale.decibel.fraction($0) }

        XCTAssertEqual(fractions, fractions.sorted())
    }

    func testDecibelScaleKeepsSilenceAtZero() {
        XCTAssertEqual(WaveformScale.decibel.fraction(0), 0)
        // Below the floor is floor, so genuine silence still reads as silence.
        XCTAssertEqual(WaveformScale.decibel.fraction(0.0001), 0)
    }

    func testScalePreservesSign() {
        XCTAssertLessThan(WaveformScale.decibel.fraction(-0.2), 0)
        XCTAssertGreaterThan(WaveformScale.decibel.fraction(0.2), 0)
        XCTAssertEqual(
            WaveformScale.decibel.fraction(-0.2),
            -WaveformScale.decibel.fraction(0.2),
            accuracy: 0.0001
        )
    }

    func testScaleClampsValuesAboveFullScale() {
        XCTAssertEqual(WaveformScale.decibel.fraction(3.0), 1.0, accuracy: 0.0001)
        XCTAssertEqual(WaveformScale.linear.fraction(3.0), 1.0, accuracy: 0.0001)
    }

    func testNonFiniteAmplitudeDrawsNothing() {
        // Garbage in a sample is treated as absence rather than as full scale, so one bad
        // value can't paint a spike across the lane.
        XCTAssertEqual(WaveformScale.decibel.fraction(.nan), 0)
        XCTAssertEqual(WaveformScale.decibel.fraction(.infinity), 0)
        XCTAssertEqual(WaveformScale.linear.fraction(.nan), 0)
    }

    // MARK: - Reduction for zooming out

    func testReductionTakesMinOfMinsAndMaxOfMaxes() {
        let peaks = WaveformPeaks(
            bucketsPerSecond: 4,
            minima: [-0.1, -0.9, -0.2, -0.3],
            maxima: [0.4, 0.2, 0.8, 0.1],
            rms: [0.2, 0.5, 0.4, 0.1],
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
            rms: [0, 0.3, 0, 0],
            coverage: [false, true, false, false]
        )

        let reduced = peaks.reduced(toAtMost: 2)

        XCTAssertEqual(reduced.coverage, [true, false])
    }

    func testReductionToMoreBucketsThanExistIsANoOp() {
        let peaks = WaveformPeaks(bucketsPerSecond: 4, minima: [0], maxima: [1], rms: [0.5], coverage: [true])
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
            rms: Array(repeating: 0, count: 250),
            coverage: Array(repeating: true, count: 250)
        )

        XCTAssertEqual(peaks.duration, 2.5)
    }
}
