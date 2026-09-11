import Foundation

/// A timestamped transcript, persisted as `transcript.json`.
///
/// Times are in **mic media time**, because that is what the engine that produced it saw.
/// `SessionEdit.micTimeOffset` converts to session time; everything that positions a cue on
/// the timeline goes through that rather than assuming the two agree.
struct Transcript: Codable, Equatable, Sendable {
    /// v2 added stable word ids and stopped storing Whisper's raw special tokens in cue text.
    /// A v1 file is discarded rather than migrated: its text is polluted with
    /// `<|startoftranscript|>`-style markup that the agent was reading as if it were speech,
    /// and re-running the model produces something correct rather than something patched.
    static let currentSchemaVersion = 2

    /// Words are the finest unit the model reports timing for, and the finest unit that is
    /// audibly sensible to cut. `id` is stable across the whole transcript so the agent can
    /// address a word exactly, instead of round-tripping a float through JSON and hoping the
    /// match survives — which is how a keyframe at 84.5001 became unaddressable.
    struct Word: Codable, Equatable, Sendable, Identifiable {
        var id: Int
        var start: TimeInterval
        var end: TimeInterval
        var text: String

        var span: TimeSpan { TimeSpan(start: start, end: end) }
    }

    struct Segment: Codable, Equatable, Sendable, Identifiable {
        var id: Int
        var start: TimeInterval
        var end: TimeInterval
        var text: String
        var words: [Word]

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

    // MARK: - Lookup

    var allWords: [Word] { segments.flatMap(\.words) }

    var wordsByID: [Int: Word] {
        Dictionary(allWords.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
    }

    func words(in span: TimeSpan) -> [Word] {
        allWords.filter { $0.start < span.end && $0.end > span.start }
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

    // MARK: - Cleaning
    //
    // Whisper emits control markup inline in its text (`<|startoftranscript|>`, `<|en|>`,
    // `<|3.42|>`) and will hallucinate speech over trailing silence. Neither belongs in
    // something an agent reads as a record of what was said.

    /// Strips `<|…|>` markup and collapses the whitespace it leaves behind.
    static func cleaned(_ text: String) -> String {
        text
            .replacingOccurrences(of: "<\\|[^|]*\\|>", with: " ", options: .regularExpression)
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Drops anything the model placed outside the recording, and anything left empty once
    /// cleaned, then renumbers so ids stay dense and stable for this file.
    static func normalized(segments: [Segment], mediaDuration: TimeInterval?) -> [Segment] {
        var nextWordID = 0
        var result: [Segment] = []

        for segment in segments.sorted(by: { $0.start < $1.start }) {
            if let mediaDuration, segment.start >= mediaDuration { continue }

            let words = segment.words
                .filter { word in
                    guard word.end > word.start else { return false }
                    guard let mediaDuration else { return true }
                    return word.start < mediaDuration
                }
                .map { word -> Word in
                    var copy = word
                    copy.id = nextWordID
                    nextWordID += 1
                    copy.text = cleaned(word.text)
                    if let mediaDuration { copy.end = min(copy.end, mediaDuration) }
                    return copy
                }
                .filter { !$0.text.isEmpty }

            // Prefer text rebuilt from the words: the words carry clean text while the
            // segment's own does not, and this keeps the two from ever disagreeing.
            let text = words.isEmpty ? cleaned(segment.text) : words.map(\.text).joined(separator: " ")
            guard !text.isEmpty, !text.contains("[BLANK_AUDIO]") else {
                nextWordID -= words.count
                continue
            }

            var copy = segment
            copy.id = result.count
            copy.text = text
            copy.words = words
            copy.start = words.first?.start ?? segment.start
            copy.end = words.last?.end ?? min(segment.end, mediaDuration ?? segment.end)
            result.append(copy)
        }

        return result
    }

    static func load(from url: URL) -> Transcript? {
        guard
            let data = try? Data(contentsOf: url),
            let transcript = try? JSONDecoder().decode(Transcript.self, from: data),
            transcript.schemaVersion == currentSchemaVersion
        else { return nil }
        return transcript
    }

    func write(to url: URL) {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        guard let data = try? encoder.encode(self) else { return }
        try? data.write(to: url, options: .atomic)
    }
}
