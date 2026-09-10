import Foundation

enum TimeFormatting {
    /// `m:ss.t` — tenths matter here because the user is lining edits up against speech.
    static func timecode(_ seconds: TimeInterval) -> String {
        guard seconds.isFinite, seconds >= 0 else { return "0:00.0" }
        let minutes = Int(seconds) / 60
        let remainder = seconds - Double(minutes * 60)
        return String(format: "%d:%04.1f", minutes, remainder)
    }
}
