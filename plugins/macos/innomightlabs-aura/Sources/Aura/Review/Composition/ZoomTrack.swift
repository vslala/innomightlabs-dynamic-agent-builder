import Foundation

/// Where the zoom is at one instant. Pure, so the preview, the export and the tests agree.
///
/// Each segment contributes a blend factor that rises over its first `easeSeconds`, holds at 1,
/// and falls over its last. Where segments overlap the strongest wins — never a sum, which would
/// push the rect outside the frame. The frame at that instant is the full frame blended toward
/// that segment's rect.
enum ZoomTrack {
    /// Smoothstep: zero slope at both ends, so the move starts and stops gently.
    static func eased(_ x: Double) -> Double {
        let t = min(max(x, 0), 1)
        return t * t * (3 - 2 * t)
    }

    static func factor(of segment: ZoomSegment, at time: TimeInterval) -> Double {
        let span = segment.span
        guard span.duration > 0, time >= span.start, time < span.end else { return 0 }
        // Never longer than half the span, or the rise and the fall would overlap each other.
        let ease = min(segment.easeSeconds, span.duration / 2)
        guard ease > 0 else { return 1 }
        let rising = eased((time - span.start) / ease)
        let falling = eased((span.end - time) / ease)
        return min(rising, falling)
    }

    static func rect(at time: TimeInterval, in segments: [ZoomSegment]) -> NormalizedRect {
        var best: (factor: Double, segment: ZoomSegment)?
        for segment in segments {
            let f = factor(of: segment, at: time)
            if f > (best?.factor ?? 0) { best = (f, segment) }
        }
        guard let best else { return SessionEdit.fullFrame }
        return blend(from: SessionEdit.fullFrame, to: best.segment.rect, amount: best.factor)
    }

    static func blend(from a: NormalizedRect, to b: NormalizedRect, amount: Double) -> NormalizedRect {
        func mix(_ x: Double, _ y: Double) -> Double { x + (y - x) * amount }
        return NormalizedRect(x: mix(a.x, b.x), y: mix(a.y, b.y), width: mix(a.width, b.width), height: mix(a.height, b.height))
    }
}
