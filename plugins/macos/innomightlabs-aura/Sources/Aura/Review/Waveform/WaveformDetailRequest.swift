import Foundation

/// Decides when the cached envelope is too coarse to draw and what to fetch instead.
///
/// Pure, so the thresholds are testable rather than buried in a view.
enum WaveformDetailRequest {
    /// Below this many stored buckets across the view, the envelope draws as steps rather
    /// than a waveform. Roughly one bucket per 4 points of width.
    static let minimumBucketsPerPoint = 0.25
    /// Ceiling on requested resolution. Beyond about one bucket per point there is nothing
    /// more to see, and each bucket costs a line to draw.
    static let maximumBucketsPerSecond = 8_000

    /// The resolution to re-read the window at, or nil when the cache is good enough.
    static func bucketsPerSecond(
        visibleDuration: TimeInterval,
        viewWidth: CGFloat,
        cachedBucketsPerSecond: Int
    ) -> Int? {
        guard visibleDuration > 0, viewWidth > 1 else { return nil }

        let cachedBucketsInView = Double(cachedBucketsPerSecond) * visibleDuration
        guard cachedBucketsInView < Double(viewWidth) * minimumBucketsPerPoint else { return nil }

        // One bucket per point of width is the most that can be displayed.
        let wanted = Int((Double(viewWidth) / visibleDuration).rounded())
        return min(max(wanted, cachedBucketsPerSecond), maximumBucketsPerSecond)
    }
}
