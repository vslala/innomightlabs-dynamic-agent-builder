import Foundation

/// A timestamped transcript, persisted as `transcript.json`.
///
/// Times are in **mic media time**, because that is what the engine that produced it saw.
/// `ReviewViewModel.transcriptOffset` converts to session time — it must match the offset the
/// composition applies to the microphone lane, or an edit made from a transcript time lands
/// somewhere other than the words it names.
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

    // MARK: - Identity

    /// A fingerprint of the word sequence, used to tell whether a saved edit's word ids still
    /// mean what they meant when it was authored.
    ///
    /// Word ids are positional, so re-running the model renumbers everything: a cut recorded
    /// against id 57 would silently re-derive onto whatever word is 57th this time, moving the
    /// cut onto unrelated audio. Comparing this string catches that.
    ///
    /// Built from the text and timing of every word rather than the file's bytes, because the
    /// same transcript re-encoded must compare equal — only a genuine re-transcription should
    /// invalidate.
    /// Deliberately FNV-1a and not `Hasher`: Swift seeds `Hasher` per process, so a
    /// `hashValue`-derived identity would differ on every launch and detach every word cut
    /// from a transcript that had not changed. This must be stable across launches and
    /// machines, because it is persisted in `edit.json`.
    var identity: String {
        let words = allWords
        var hash: UInt64 = 0xcbf2_9ce4_8422_2325

        func feed(_ bytes: some Sequence<UInt8>) {
            for byte in bytes {
                hash ^= UInt64(byte)
                hash = hash &* 0x100_0000_01b3
            }
        }

        feed("\(schemaVersion)|\(engine)|".utf8)
        for word in words {
            // Quantised to milliseconds: a re-serialised transcript can differ in the last
            // float digit without being a different transcript.
            let start = Int((word.start * 1000).rounded())
            let end = Int((word.end * 1000).rounded())
            feed("\(word.id):\(start):\(end):\(word.text)|".utf8)
        }

        return "w\(words.count)-\(String(hash, radix: 16))"
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
