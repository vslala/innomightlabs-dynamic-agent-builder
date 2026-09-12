import CoreGraphics
import Foundation
import ImageIO

/// Decodes filmstrip frames on demand, keeping the recently drawn ones.
///
/// A class rather than a struct because it is a cache: the lane redraws on every playhead tick,
/// and re-decoding the same visible JPEGs 30 times a second would be the most expensive thing
/// in the window.
final class FilmstripFrames {
    private let strip: Filmstrip
    private var decoded: [Int: CGImage] = [:]
    /// Insertion order, for eviction. A handful of frames is visible at once; the limit is
    /// generous enough to survive scrubbing without growing without bound.
    private var order: [Int] = []
    private let limit = 120

    init(_ strip: Filmstrip) {
        self.strip = strip
    }

    var frameCount: Int { strip.frameCount }
    var interval: TimeInterval { strip.interval }
    var frameAspect: CGFloat {
        guard strip.frameSize.height > 0 else { return 16.0 / 9 }
        return strip.frameSize.width / strip.frameSize.height
    }

    func image(atSource seconds: TimeInterval) -> CGImage? {
        guard let index = strip.frameIndex(atSource: seconds) else { return nil }
        return image(at: index)
    }

    func image(at index: Int) -> CGImage? {
        if let cached = decoded[index] { return cached }
        guard index >= 0, index < strip.frames.count else { return nil }

        guard
            let source = CGImageSourceCreateWithData(strip.frames[index] as CFData, nil),
            let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
        else { return nil }

        decoded[index] = image
        order.append(index)
        if order.count > limit, let oldest = order.first {
            order.removeFirst()
            decoded.removeValue(forKey: oldest)
        }
        return image
    }
}
