import Foundation

/// Which slice of the timeline the waveform lanes show.
///
/// Pure. The window follows the playhead rather than having its own scroll position: for
/// frame-level editing you put the playhead where you're working and zoom in, which is one
/// control instead of two and can never leave the playhead off screen.
enum WaveformWindow {
    static func span(
        total: TimeInterval,
        visibleDuration: TimeInterval?,
        playhead: TimeInterval
    ) -> TimeSpan {
        guard total > 0 else { return TimeSpan(start: 0, end: 0) }
        guard let visibleDuration, visibleDuration > 0, visibleDuration < total else {
            return TimeSpan(start: 0, end: total)
        }

        // Centred on the playhead, then clamped so the window never runs past either end —
        // which is what keeps the first and last moments of a recording reachable.
        let centre = min(max(0, playhead), total)
        let start = min(max(0, centre - visibleDuration / 2), total - visibleDuration)
        return TimeSpan(start: start, end: start + visibleDuration)
    }
}
