import Foundation

/// Decides when the timeline window should move to keep the playhead in view.
///
/// Pure, so the behaviour can be pinned without a player. Separated from the view model
/// because the interesting part is not the scrolling but the *policy*, and the policy is
/// counter-intuitive: tracking the playhead continuously is the obvious implementation and the
/// wrong one.
///
/// The timeline's axis is the recording, not the edited timeline, so during playback the
/// playhead jumps across every cut — over a hundred times per playthrough on a real document.
/// Tracking each jump pans the view constantly and re-reads the waveform at display resolution
/// every time. Paging moves the window only when the playhead actually leaves it, which turns
/// that into a handful of moves: a cut jump inside the visible window costs nothing at all.
enum PlayheadFollower {
    /// How far in from the leading edge the playhead lands when the window pages.
    ///
    /// Small, so a page-turn buys almost a full window of lookahead. Centring instead would
    /// halve how long the view stays put and double the number of moves.
    static let leadInFraction: Double = 0.12

    /// Where the window should start, or nil to leave it alone.
    ///
    /// - Parameters:
    ///   - playhead: the playhead in recording time.
    ///   - window: the visible span, in recording time.
    ///   - recordingDuration: the full extent, for clamping at the end.
    ///   - leadInFraction: how far in from the leading edge the playhead should land.
    static func viewportStart(
        playhead: TimeInterval,
        window: (start: TimeInterval, duration: TimeInterval),
        recordingDuration: TimeInterval,
        leadInFraction: Double
    ) -> TimeInterval? {
        guard window.duration > 0, window.duration < recordingDuration else { return nil }

        // Half-open, matching the rest of the timeline: a playhead exactly on the trailing
        // edge is already outside and should page.
        let isVisible = playhead >= window.start && playhead < window.start + window.duration
        guard !isVisible else { return nil }

        let proposed = playhead - window.duration * leadInFraction
        let limit = max(0, recordingDuration - window.duration)
        return min(max(0, proposed), limit)
    }
}
