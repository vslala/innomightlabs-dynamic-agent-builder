import Foundation

/// Items in a reply that are not edits.
///
/// The agent can ask for more transcript, or ask Aura to find words for it. Keeping these out
/// of `EditOperation` matters: an operation must be applicable to a `SessionEdit` alone, and
/// both of these need the transcript to mean anything.
enum AgentRequest: Equatable, Sendable {
    /// Word detail for another range. Aura answers by sending a follow-up turn.
    case transcript(TimeSpan)
    /// Find every instance of these words in a range and propose cutting them, so the agent
    /// doesn't have to enumerate ids — scoped, because an unscoped sweep takes out words that
    /// carried meaning.
    case fillerSweep(words: [String], span: TimeSpan?, why: String?)

    private enum Key: String {
        case requestTranscript = "request_transcript"
        case excludeFillerWords = "exclude_filler_words"
    }

    /// Decodes a request from one raw operation object, or nil if it isn't one.
    static func from(json object: [String: Any]) -> AgentRequest? {
        guard let op = object["op"] as? String, let key = Key(rawValue: op) else { return nil }

        let from = (object["from"] as? Double) ?? (object["start"] as? Double)
        let to = (object["to"] as? Double) ?? (object["end"] as? Double)

        switch key {
        case .requestTranscript:
            guard let from, let to, to > from else { return nil }
            return .transcript(TimeSpan(start: from, end: to))

        case .excludeFillerWords:
            let words = (object["words"] as? [Any] ?? [])
                .compactMap { $0 as? String }
                .map { $0.trimmingCharacters(in: .whitespaces).lowercased() }
                .filter { !$0.isEmpty }
            guard !words.isEmpty else { return nil }

            let span: TimeSpan? = {
                guard let from, let to, to > from else { return nil }
                return TimeSpan(start: from, end: to)
            }()
            return .fillerSweep(words: words, span: span, why: object["why"] as? String)
        }
    }
}

/// Turns agent requests into concrete suggestions, using the transcript the agent can't see
/// in full.
enum AgentRequestResolver {
    /// Punctuation the model attaches to words ("so," / "um."), stripped before matching so
    /// the agent can ask for "so" and still find it.
    private static let strippable = CharacterSet(charactersIn: ",.?!;:…\"'“”‘’-–—")

    static func normalized(_ text: String) -> String {
        text.trimmingCharacters(in: .whitespaces)
            .trimmingCharacters(in: strippable)
            .lowercased()
    }

    /// Every word in `span` whose text matches one of `words`, as a single suggestion.
    ///
    /// One suggestion rather than one per word, so accepting is a single decision and a single
    /// undo step — and the summary names what will go, so it is still reviewable.
    static func resolveFillerSweep(
        words targets: [String],
        span: TimeSpan?,
        why: String?,
        transcript: Transcript?,
        micTimeOffset: TimeInterval,
        alreadyExcluded: Set<Int>
    ) -> EditSuggestion? {
        guard let transcript else { return nil }
        let wanted = Set(targets.map(normalized))

        let matches = transcript.allWords.compactMap { word -> ExcludedWord? in
            guard !alreadyExcluded.contains(word.id) else { return nil }
            guard wanted.contains(normalized(word.text)) else { return nil }

            // Into session time, the clock the document and the operations use.
            let start = word.start + micTimeOffset
            let end = word.end + micTimeOffset
            if let span, start >= span.end || end <= span.start { return nil }

            return ExcludedWord(id: word.id, start: start, end: end, text: word.text)
        }

        guard !matches.isEmpty else { return nil }
        let scope = span.map { String(format: " between %.1fs and %.1fs", $0.start, $0.end) } ?? ""
        return EditSuggestion(
            operation: .excludeWords(matches),
            rationale: why ?? "Filler words\(scope)"
        )
    }
}
