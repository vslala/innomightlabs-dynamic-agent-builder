import CoreMedia
import Foundation

/// One of the review layer's time bases.
///
/// There are three, and confusing them has caused three separate shipped bugs. Making the
/// clock part of the *type* means a view cannot convert between them by accident: there is no
/// operator that crosses clocks, and the only conversions in the program are methods on
/// `ReviewProjection`.
protocol ReviewClock: Sendable {
    static var clockName: String { get }
}

/// Position on the edited timeline — what `AVPlayer` reports and seeks to.
enum Composition: ReviewClock {
    static let clockName = "composition"
}

/// Position in the original recording. What cuts, splits, markers and clips are expressed in.
enum Source: ReviewClock {
    static let clockName = "source"
}

/// Position in the raw microphone file, which is the clock the transcript is stamped in.
/// Differs from `Source` by the microphone lane's offset.
enum MicMedia: ReviewClock {
    static let clockName = "micMedia"
}

/// A point in time, tagged with the clock it belongs to.
///
/// Arithmetic is deliberately limited to staying inside one clock: two stamps of the same
/// clock can be compared and subtracted to a `TimeInterval`, and a `TimeInterval` can be added
/// to a stamp. There is no way to turn a `Stamp<Composition>` into a `Stamp<Source>` other
/// than asking the projection, which is the whole point.
struct Stamp<C: ReviewClock>: Equatable, Hashable, Comparable, Sendable {
    let seconds: TimeInterval

    init(_ seconds: TimeInterval) {
        self.seconds = seconds.isFinite ? seconds : 0
    }

    init(_ time: CMTime) {
        self.init(Timeline.seconds(time))
    }

    var cm: CMTime { Timeline.time(seconds: seconds) }

    static var zero: Stamp<C> { Stamp(0) }

    static func < (lhs: Stamp<C>, rhs: Stamp<C>) -> Bool { lhs.seconds < rhs.seconds }

    /// Distance between two points on the same clock.
    static func - (lhs: Stamp<C>, rhs: Stamp<C>) -> TimeInterval { lhs.seconds - rhs.seconds }

    static func + (lhs: Stamp<C>, rhs: TimeInterval) -> Stamp<C> { Stamp(lhs.seconds + rhs) }
    static func - (lhs: Stamp<C>, rhs: TimeInterval) -> Stamp<C> { Stamp(lhs.seconds - rhs) }

    func clamped(to span: StampSpan<C>) -> Stamp<C> {
        Stamp(min(max(seconds, span.start.seconds), span.end.seconds))
    }
}

/// A half-open span `[start, end)` on one clock.
struct StampSpan<C: ReviewClock>: Equatable, Hashable, Sendable {
    var start: Stamp<C>
    var end: Stamp<C>

    init(start: Stamp<C>, end: Stamp<C>) {
        self.start = start
        self.end = end
    }

    init(start: TimeInterval, end: TimeInterval) {
        self.init(start: Stamp(start), end: Stamp(end))
    }

    var duration: TimeInterval { max(0, end - start) }
    var isEmpty: Bool { end <= start }

    func contains(_ stamp: Stamp<C>) -> Bool { stamp >= start && stamp < end }

    func overlaps(_ other: StampSpan<C>) -> Bool { start < other.end && end > other.start }

    /// Where `stamp` sits within the span, as 0...1. Used for time→pixel mapping, which is the
    /// only arithmetic a view should be doing with time at all.
    func fraction(of stamp: Stamp<C>) -> Double {
        guard duration > 0 else { return 0 }
        return min(1, max(0, (stamp - start) / duration))
    }

    /// The inverse: a fraction of the span back to a stamp. For hit-testing a click.
    func stamp(atFraction fraction: Double) -> Stamp<C> {
        start + min(1, max(0, fraction)) * duration
    }
}

extension StampSpan where C == Source {
    /// Bridges to the document's untagged `TimeSpan`, which is in source time.
    init(_ span: TimeSpan) {
        self.init(start: span.start, end: span.end)
    }

    var timeSpan: TimeSpan { TimeSpan(start: start.seconds, end: end.seconds) }
}
