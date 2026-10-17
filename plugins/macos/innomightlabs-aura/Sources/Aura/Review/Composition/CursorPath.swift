import CoreGraphics
import Foundation

/// Where the rendered cursor is, and how far its click ripple has spread, at one session time.
///
/// Built from the recorded pointer events. The host already applied the easing, so this only
/// joins the dots: it interpolates linearly between consecutive moves, because the events arrive
/// at roughly 40 Hz and the picture is rendered at 60.
///
/// Positions are normalized against the **source** screen frame, top-left origin, so the
/// compositor can place them through the same crop and zoom as the picture. Pointer events are
/// CSS pixels and are mapped here through the viewport the take was calibrated against.
struct CursorPath: Equatable, Sendable {
    struct Point: Equatable, Sendable {
        let t: TimeInterval
        let position: CGPoint
    }

    /// How long a click ripple takes to spread and fade.
    static let rippleDuration: TimeInterval = 0.5

    private(set) var moves: [Point]
    private(set) var clicks: [Point]

    /// - Parameter rippleSteps: the steps whose clicks make a ripple. Nil means every click does, for a
    ///   take whose spec is not known.
    init(log: ActionLog, viewport: BrowserViewportMetadata, rippleSteps: Set<String>? = nil) {
        let frame = viewport.frameSize
        func normalized(_ cssPoint: CGPoint) -> CGPoint? {
            guard frame.width > 0, frame.height > 0 else { return nil }
            let window = viewport.windowPoint(forCSSPoint: cssPoint)
            return CGPoint(x: window.x / frame.width, y: window.y / frame.height)
        }

        var moves: [Point] = []
        var clicks: [Point] = []
        for entry in log.entries {
            guard let css = entry.point, let position = normalized(css) else { continue }
            switch entry.kind {
            case .mouseMove: moves.append(Point(t: entry.t, position: position))
            case .mouseDown:
                // A click also places the pointer, so the path reaches the click even when the
                // host sent no final move.
                moves.append(Point(t: entry.t, position: position))
                if rippleSteps?.contains(entry.stepID) ?? true {
                    clicks.append(Point(t: entry.t, position: position))
                }
            default: break
            }
        }
        self.moves = moves.sorted { $0.t < $1.t }
        self.clicks = clicks
    }

    var isEmpty: Bool { moves.isEmpty }

    /// Nil before the first pointer event: a cursor that appears at a made-up spot is worse
    /// than none.
    func position(at time: TimeInterval) -> CGPoint? {
        guard let first = moves.first, time >= first.t else { return nil }
        guard let next = moves.firstIndex(where: { $0.t > time }) else { return moves.last?.position }
        let previous = moves[next - 1]
        let following = moves[next]
        let span = following.t - previous.t
        guard span > 0 else { return previous.position }
        let f = (time - previous.t) / span
        return CGPoint(
            x: previous.position.x + (following.position.x - previous.position.x) * f,
            y: previous.position.y + (following.position.y - previous.position.y) * f
        )
    }

    /// Every ripple still visible at `time`: where it is and how far through it is, 0...1.
    func ripples(at time: TimeInterval) -> [(position: CGPoint, progress: Double)] {
        clicks.compactMap { click in
            let age = time - click.t
            guard age >= 0, age < Self.rippleDuration else { return nil }
            return (click.position, age / Self.rippleDuration)
        }
    }
}
