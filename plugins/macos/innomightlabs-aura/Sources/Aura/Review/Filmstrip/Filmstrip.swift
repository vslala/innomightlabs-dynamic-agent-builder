import CoreGraphics
import Foundation

/// Thumbnails for one video track, evenly spaced across the recording.
///
/// Frames stay JPEG-encoded in memory and are decoded only when drawn: the strip holds up to
/// `maxFrames` thumbnails and a lane shows a few dozen, so decoding all of them to draw 40
/// would be waste that scales with recording length.
struct Filmstrip: Sendable {
    /// Frame interval in source seconds. Bucket 0 is centred at `interval / 2`.
    let interval: TimeInterval
    let frameSize: CGSize
    /// JPEG payloads, in time order.
    let frames: [Data]

    /// Roughly one frame every two seconds, so the strip reads as continuous motion at a
    /// normal zoom without extracting more than can be cached cheaply.
    static let targetInterval: TimeInterval = 2
    static let minimumInterval: TimeInterval = 1
    /// Bounds both extraction time and cache size: a 40-minute recording would otherwise ask
    /// for 1,200 frames of an HEVC screen capture.
    static let maxFrames = 600
    /// Small on purpose. A lane is ~40pt tall, so anything larger is downscaled at draw time.
    static let extractionSize = CGSize(width: 160, height: 90)

    var frameCount: Int { frames.count }

    /// The frame covering a source time, or nil when the time is outside what was extracted.
    func frameIndex(atSource seconds: TimeInterval) -> Int? {
        guard interval > 0, seconds >= 0 else { return nil }
        let index = Int(seconds / interval)
        return index < frames.count ? index : nil
    }

    func time(ofFrame index: Int) -> TimeInterval {
        (Double(index) + 0.5) * interval
    }

    /// How many frames to extract for a recording, and how far apart.
    static func plan(duration: TimeInterval) -> (interval: TimeInterval, count: Int) {
        guard duration > 0 else { return (targetInterval, 0) }

        let idealCount = Int((duration / targetInterval).rounded(.up))
        if idealCount <= maxFrames {
            return (max(minimumInterval, targetInterval), max(1, idealCount))
        }
        // Spread the ceiling across the whole recording rather than truncating it.
        return (duration / Double(maxFrames), maxFrames)
    }
}
