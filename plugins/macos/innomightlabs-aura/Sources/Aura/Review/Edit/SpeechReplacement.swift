import CoreMedia
import Foundation

/// A stretch of the recording re-spoken from text, in the user's own voice.
///
/// The edit is just this record. The speech itself is derived data — a clip the renderer makes
/// from `text` and keeps beside the session (`SessionFolder.speechClipURL`) — so the original
/// recording is never touched and removing the replacement is deleting a row.
struct SpeechReplacement: Codable, Hashable, Identifiable, Sendable {
    var id: UUID
    /// What is being replaced, in session time like every time in an operation.
    var span: TimeSpan
    var text: String
    /// What was said there before, kept so restoring and the transcript view never need the
    /// transcript (which describes the recording and is never rewritten).
    var originalText: String
    /// Length of the generated clip. Zero until one has been rendered: an agent suggestion
    /// arrives without audio, and accepting it renders first. Never shorter than the span once
    /// rendered, and stored rather than measured so the document alone defines the timeline.
    var duration: TimeInterval

    init(
        id: UUID = UUID(),
        span: TimeSpan,
        text: String,
        originalText: String = "",
        duration: TimeInterval = 0
    ) {
        self.id = id
        self.span = span
        self.text = text
        self.originalText = originalText
        self.duration = duration
    }

    /// Not yet spoken. Such a replacement can be suggested but not applied.
    var isDraft: Bool { duration <= 0 }

    /// How long the picture is held after the span while the extra speech finishes.
    var hold: TimeInterval { max(0, duration - span.duration) }

    /// The `TimeMap` hold this replacement asks for, or nil when the speech fits.
    var timeMapHold: TimeMap.Hold? {
        guard hold > Self.holdTolerance else { return nil }
        return TimeMap.Hold(at: Timeline.time(seconds: span.end), duration: Timeline.time(seconds: hold))
    }

    /// Below this a "hold" is rounding, not a pause in the picture.
    static let holdTolerance: TimeInterval = 1.0 / 60.0
    /// Replacing less than this is a click, not speech.
    static let minimumSpan: TimeInterval = 0.3
    /// The longest hold a document accepts. Far past anything the user would choose, so it is a
    /// guard against a runaway text, not a judgement: the UI asks long before this
    /// (`DurationFitter.confirmationThreshold`).
    static let maximumHold: TimeInterval = 60

    private enum CodingKeys: String, CodingKey {
        case id, start, end, text, originalText, duration
    }

    /// Tolerant on purpose: an agent proposes `{start, end, text}` and nothing else, and the rest
    /// is filled in when the suggestion is accepted and rendered.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        span = TimeSpan(
            start: try container.decode(TimeInterval.self, forKey: .start),
            end: try container.decode(TimeInterval.self, forKey: .end)
        )
        text = try container.decode(String.self, forKey: .text)
        originalText = try container.decodeIfPresent(String.self, forKey: .originalText) ?? ""
        duration = try container.decodeIfPresent(TimeInterval.self, forKey: .duration) ?? 0
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(span.start, forKey: .start)
        try container.encode(span.end, forKey: .end)
        try container.encode(text, forKey: .text)
        try container.encode(originalText, forKey: .originalText)
        try container.encode(duration, forKey: .duration)
    }
}
