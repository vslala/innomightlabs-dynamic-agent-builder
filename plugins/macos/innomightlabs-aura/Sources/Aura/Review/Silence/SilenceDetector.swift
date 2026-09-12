import Foundation

/// Finds the quiet stretches in a waveform envelope.
///
/// Pure, over plain bucket levels, so it tests without audio and without AVFoundation. The
/// caller converts bucket indices to source time through the projection — never by hand, which
/// is how the last clock bug happened.
enum SilenceDetector {
    struct Options: Equatable, Sendable {
        /// Anything quieter than this counts as silence. −40 dBFS sits below room tone but
        /// above the noise floor of a normal microphone.
        var floorDecibels: Double = -40
        /// Shorter gaps are the natural rhythm of speech. Cutting them makes narration sound
        /// clipped and unnatural, which is worse than leaving them.
        var minimumDuration: TimeInterval = 0.35
        /// Left at each end of a detected gap, so the cut does not clip the tail of the word
        /// before it or the attack of the word after.
        var padding: TimeInterval = 0.1

        static let `default` = Options()
    }

    /// - Parameters:
    ///   - levels: linear RMS per bucket, as `WaveformPeaks` stores it.
    ///   - secondsPerBucket: the envelope's time resolution.
    ///   - coverage: false where the source had no samples at all (a muted span). Treated as
    ///     *not* silence — there is nothing there to remove, and proposing a cut over a gap the
    ///     recorder already left would be confusing.
    /// - Returns: spans to remove, in **audio-file** time, non-overlapping and in order.
    static func silences(
        levels: [Double],
        secondsPerBucket: TimeInterval,
        coverage: [Bool]? = nil,
        options: Options = .default
    ) -> [TimeSpan] {
        guard secondsPerBucket > 0, !levels.isEmpty else { return [] }

        let threshold = pow(10, options.floorDecibels / 20)
        var spans: [TimeSpan] = []
        var runStart: Int?

        func closeRun(at end: Int) {
            guard let start = runStart else { return }
            runStart = nil

            let rawStart = Double(start) * secondsPerBucket
            let rawEnd = Double(end) * secondsPerBucket
            guard rawEnd - rawStart >= options.minimumDuration else { return }

            // Padding is applied after the length test, so a gap that only qualifies because
            // of padding is not cut.
            let paddedStart = rawStart + options.padding
            let paddedEnd = rawEnd - options.padding
            guard paddedEnd > paddedStart else { return }

            spans.append(TimeSpan(start: paddedStart, end: paddedEnd))
        }

        for index in levels.indices {
            let covered = coverage.map { index < $0.count ? $0[index] : false } ?? true
            let isQuiet = covered && levels[index] < threshold

            if isQuiet {
                if runStart == nil { runStart = index }
            } else {
                closeRun(at: index)
            }
        }
        closeRun(at: levels.count)

        return spans
    }
}
