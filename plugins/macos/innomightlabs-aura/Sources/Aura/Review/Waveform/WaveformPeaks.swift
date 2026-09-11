import Foundation

/// A peak envelope for one audio lane.
///
/// `coverage` is what distinguishes "the mic was muted here" from "the room was quiet here":
/// muting during recording skips the writer append entirely, so those buckets are never
/// written rather than being written as zeroes.
struct WaveformPeaks: Equatable, Sendable {
    /// 100 gives finer resolution than one video frame, so zooming in never needs a re-read
    /// of the file — zooming out is a pure min/max reduction over these buckets, which is
    /// exact, unlike decoding again at a coarser rate.
    static let defaultBucketsPerSecond = 100

    let bucketsPerSecond: Int
    let minima: [Float]
    let maxima: [Float]
    /// Root-mean-square per bucket — the loudness of the bucket rather than its extreme.
    /// Drawn as a solid inner band over the lighter peak envelope, which is what gives an
    /// Audacity-style waveform its readable body: peaks alone are spiky and say little about
    /// where speech actually is.
    let rms: [Float]
    let coverage: [Bool]

    var bucketCount: Int { maxima.count }
    var duration: TimeInterval {
        bucketsPerSecond > 0 ? Double(bucketCount) / Double(bucketsPerSecond) : 0
    }

    static let empty = WaveformPeaks(
        bucketsPerSecond: defaultBucketsPerSecond,
        minima: [],
        maxima: [],
        rms: [],
        coverage: []
    )

    /// Reduces to at most `count` buckets by taking the min of mins and max of maxes. Pure,
    /// and exact — this is why the cache is stored fine-grained.
    func reduced(toAtMost count: Int) -> WaveformPeaks {
        guard count > 0, bucketCount > count else { return self }

        let stride = Double(bucketCount) / Double(count)
        var minima: [Float] = []
        var maxima: [Float] = []
        var rms: [Float] = []
        var coverage: [Bool] = []
        minima.reserveCapacity(count)
        maxima.reserveCapacity(count)
        rms.reserveCapacity(count)
        coverage.reserveCapacity(count)

        for index in 0..<count {
            let lower = Int(Double(index) * stride)
            let upper = min(bucketCount, max(lower + 1, Int(Double(index + 1) * stride)))
            let range = lower..<upper

            minima.append(self.minima[range].min() ?? 0)
            maxima.append(self.maxima[range].max() ?? 0)
            // Quadratic mean, since averaging RMS values directly would understate loudness.
            let squares = self.rms[range].reduce(0.0) { $0 + Double($1) * Double($1) }
            rms.append(Float((squares / Double(range.count)).squareRoot()))
            coverage.append(self.coverage[range].contains(true))
        }

        return WaveformPeaks(
            bucketsPerSecond: Int((Double(bucketsPerSecond) / stride).rounded()),
            minima: minima,
            maxima: maxima,
            rms: rms,
            coverage: coverage
        )
    }
}

/// Buckets interleaved PCM into a peak envelope.
///
/// No AVFoundation or CoreMedia types in the signature: the caller works out which sample
/// index a buffer starts at and this only does arithmetic, which is what makes it testable.
struct PeakAccumulator {
    private let samplesPerBucket: Double
    private var minima: [Float]
    private var maxima: [Float]
    private var sumSquares: [Double]
    private var counts: [Int]
    private var coverage: [Bool]
    private let bucketsPerSecond: Int

    init(bucketCount: Int, samplesPerBucket: Double, bucketsPerSecond: Int) {
        let count = max(0, bucketCount)
        // Deliberately a Double: many bucket sizes don't divide the sample rate evenly, and
        // integer truncation would accumulate visible drift over a long recording.
        self.samplesPerBucket = max(1, samplesPerBucket)
        self.bucketsPerSecond = bucketsPerSecond
        minima = Array(repeating: 0, count: count)
        maxima = Array(repeating: 0, count: count)
        sumSquares = Array(repeating: 0, count: count)
        counts = Array(repeating: 0, count: count)
        coverage = Array(repeating: false, count: count)
    }

    /// - Parameter firstSampleIndex: the absolute index of the first frame in this buffer,
    ///   derived from its presentation timestamp — never from a running count. Edit lists mean
    ///   the two disagree wherever the recording was muted.
    mutating func accumulate(
        _ samples: UnsafeBufferPointer<Float>,
        channelCount: Int,
        firstSampleIndex: Int
    ) {
        guard !minima.isEmpty, channelCount > 0 else { return }

        let frames = samples.count / channelCount
        for frame in 0..<frames {
            let bucket = Int(Double(firstSampleIndex + frame) / samplesPerBucket)
            guard bucket >= 0, bucket < minima.count else { continue }

            for channel in 0..<channelCount {
                let value = samples[frame * channelCount + channel]
                guard value.isFinite else { continue }
                if !coverage[bucket] {
                    coverage[bucket] = true
                    minima[bucket] = value
                    maxima[bucket] = value
                } else {
                    minima[bucket] = Swift.min(minima[bucket], value)
                    maxima[bucket] = Swift.max(maxima[bucket], value)
                }
                sumSquares[bucket] += Double(value) * Double(value)
                counts[bucket] += 1
            }
        }
    }

    mutating func accumulate(_ samples: [Float], channelCount: Int, firstSampleIndex: Int) {
        samples.withUnsafeBufferPointer {
            accumulate($0, channelCount: channelCount, firstSampleIndex: firstSampleIndex)
        }
    }

    func finish() -> WaveformPeaks {
        WaveformPeaks(
            bucketsPerSecond: bucketsPerSecond,
            minima: minima,
            maxima: maxima,
            rms: zip(sumSquares, counts).map { squares, count in
                count > 0 ? Float((squares / Double(count)).squareRoot()) : 0
            },
            coverage: coverage
        )
    }
}
