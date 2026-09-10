import CoreMedia
import Foundation

/// The one timescale every time in the edit layer is expressed on.
///
/// The edit document stores seconds, because it is also the wire format the agent reads and
/// writes and seconds are what an agent can reason about. All *arithmetic*, though, happens
/// on `CMTime` at this fixed timescale: clip boundaries then compare as exact integers, so a
/// cut lands on one frame rather than flickering between two.
///
/// 90_000 is divisible by 24, 25, 30, 50, and 60. The classic QuickTime 600 is not divisible
/// by 44_100, which would make sample-accurate audio trims drift.
enum Timeline {
    static let timescale: CMTimeScale = 90_000

    static let frameDuration = CMTime(value: 1, timescale: 30)

    static func time(seconds: TimeInterval) -> CMTime {
        guard seconds.isFinite else { return .zero }
        return normalized(CMTime(seconds: seconds, preferredTimescale: timescale))
    }

    /// Snaps a time onto `timescale`. Also the guard that keeps non-numeric `CMTime`s out of
    /// the composition layer, where they would raise an uncatchable ObjC exception.
    static func normalized(_ time: CMTime) -> CMTime {
        guard time.isNumeric else { return .zero }
        guard time.timescale != timescale else { return time }
        return CMTimeConvertScale(time, timescale: timescale, method: .roundHalfAwayFromZero)
    }

    static func seconds(_ time: CMTime) -> TimeInterval {
        time.isNumeric ? CMTimeGetSeconds(time) : 0
    }
}
