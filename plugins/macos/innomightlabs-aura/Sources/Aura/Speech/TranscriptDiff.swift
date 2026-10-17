import Foundation

/// Works out what an edit to the transcript means for the recording.
///
/// The unit of replacement is the cue the user edited: the model re-speaks whole sentences, so
/// changing one word means speaking the cue again. Pure — the transcript view hands over text
/// and this hands back a draft.
enum TranscriptDiff {
    /// The text a cue was changed to, or nil when nothing worth re-speaking changed.
    ///
    /// Whitespace-only edits do not count: re-speaking a sentence the user did not change would
    /// cost a render and replace their real voice with a copy of it.
    static func changedText(from old: String, to new: String) -> String? {
        let before = normalized(old)
        let after = normalized(new)
        guard !after.isEmpty, before != after else { return nil }
        return after
    }

    /// The selection a cue covers, in session time.
    ///
    /// From the first word's start to the last word's end rather than the cue's own times,
    /// which include the model's padding and would silence a breath on either side.
    ///
    /// - Parameter micOffset: converts the transcript's clock to session time.
    static func span(of cue: Transcript.Segment, micOffset: TimeInterval) -> TimeSpan? {
        guard let first = cue.words.first, let last = cue.words.last, last.end > first.start else { return nil }
        return TimeSpan(start: first.start + micOffset, end: last.end + micOffset)
    }

    private static func normalized(_ text: String) -> String {
        text.split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }
}

extension SessionEdit {
    /// Whether the camera is on screen at any moment of `span`. New words will not match the
    /// speaker's mouth there, which is worth saying before it is done.
    func cameraIsVisible(during span: TimeSpan) -> Bool {
        if overlay(at: span.start)?.visible == true { return true }
        return cameraOverlay.contains { $0.visible && $0.t > span.start && $0.t < span.end }
    }
}
