import Foundation

/// A timestamped transcript, persisted as `transcript.json`.
///
/// Times are in **mic media time**, because that is what the engine that produced it saw.
/// `SessionEdit.micTimeOffset` converts to session time; everything that positions a cue on
/// the timeline goes through that rather than assuming the two agree.
struct Transcript: Codable, Equatable, Sendable {
    static let currentSchemaVersion = 1

    struct Word: Codable, Equatable, Sendable {
        var start: TimeInterval
        var end: TimeInterval
        var text: String
    }

    /// Word timings are kept because they are what later makes "delete this sentence" a
    /// precise edit rather than an approximate one.
    struct Segment: Codable, Equatable, Sendable, Identifiable {
        var id: Int
        var start: TimeInterval
        var end: TimeInterval
        var text: String
        var words: [Word]?

        var span: TimeSpan { TimeSpan(start: start, end: end) }
    }

    var schemaVersion: Int
    var source: String
    var engine: String
    var language: String?
    var segments: [Segment]

    init(
        schemaVersion: Int = currentSchemaVersion,
        source: String,
        engine: String,
        language: String? = nil,
        segments: [Segment]
    ) {
        self.schemaVersion = schemaVersion
        self.source = source
        self.engine = engine
        self.language = language
        self.segments = segments
    }

    /// The segment covering a mic-media time. Binary search, since this runs on every
    /// playhead tick. Half-open `[start, end)` to match the rest of the timeline.
    func segment(at time: TimeInterval) -> Segment? {
        var low = 0
        var high = segments.count - 1

        while low <= high {
            let mid = (low + high) / 2
            let segment = segments[mid]
            if time < segment.start {
                high = mid - 1
            } else if time >= segment.end {
                low = mid + 1
            } else {
                return segment
            }
        }
        return nil
    }

    static func load(from url: URL) -> Transcript? {
        guard
            let data = try? Data(contentsOf: url),
            let transcript = try? JSONDecoder().decode(Transcript.self, from: data),
            transcript.schemaVersion <= currentSchemaVersion
        else { return nil }
        return transcript
    }

    func write(to url: URL) {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard let data = try? encoder.encode(self) else { return }
        try? data.write(to: url, options: .atomic)
    }
}
