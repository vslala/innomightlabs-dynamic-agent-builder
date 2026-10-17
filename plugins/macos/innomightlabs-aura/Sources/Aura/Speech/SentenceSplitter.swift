import Foundation

/// Cuts text into sentences short enough for the speech model to say in one go.
///
/// Always splits, however short the text: the model speaks a sentence at a time, and joining the
/// pieces ourselves is what lets us control the gaps. Pure, so it is tested without a model.
enum SentenceSplitter {
    /// The model fits roughly 12–16 s of speech in one pass; at a natural pace that is well over
    /// this many characters, so a sentence under it never gets chunked internally.
    static let maximumCharacters = 140

    /// Words a full stop after them does not end a sentence.
    private static let abbreviations: Set<String> = [
        "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e", "approx", "inc", "ltd", "no"
    ]
    private static let terminators: Set<Character> = [".", "!", "?", "…"]
    private static let quotes: Set<Character> = ["\"", "“", "”"]

    static func split(_ text: String) -> [String] {
        sentences(in: text).flatMap(fit)
    }

    // MARK: - Sentences

    private static func sentences(in text: String) -> [String] {
        let characters = Array(text.replacingOccurrences(of: "\n", with: " "))
        var result: [String] = []
        var current = ""
        var insideQuote = false

        for (index, character) in characters.enumerated() {
            current.append(character)
            let next = index + 1 < characters.count ? characters[index + 1] : nil

            if quotes.contains(character) {
                // A quoted brand or title stays whole, whatever punctuation it holds.
                insideQuote.toggle()
                // A quote that closes right after a full stop ends the sentence there.
                if !insideQuote, endsAfterTerminator(current), next == nil || next!.isWhitespace {
                    result.append(current)
                    current = ""
                }
                continue
            }
            guard !insideQuote, terminators.contains(character) else { continue }

            // A full stop only ends a sentence when whitespace (or the end) follows: "3.5" and
            // "innomight.com" do not. A quote right after is the closing one, handled above.
            guard next == nil || next!.isWhitespace else { continue }
            if character == ".", endsWithAbbreviation(current) { continue }

            result.append(current)
            current = ""
        }
        result.append(current)

        return result
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { $0.contains(where: \.isLetter) || $0.contains(where: \.isNumber) }
    }

    /// True when the text, ignoring a closing quote at its end, ends in sentence punctuation.
    private static func endsAfterTerminator(_ text: String) -> Bool {
        guard let last = text.dropLast().last else { return false }
        return terminators.contains(last)
    }

    private static func endsWithAbbreviation(_ sentence: String) -> Bool {
        let word = sentence.dropLast()
            .split(whereSeparator: \.isWhitespace).last
            .map { $0.lowercased().trimmingCharacters(in: CharacterSet.punctuationCharacters.subtracting(["."])) }
        guard let word else { return false }
        // A single capital initial: "J. Smith".
        if word.count == 1, word.first!.isLetter { return true }
        return abbreviations.contains(word)
    }

    // MARK: - Over-long sentences

    /// Splits a sentence that is still too long, at clause punctuation first and at spaces only
    /// if a clause is itself too long.
    private static func fit(_ sentence: String) -> [String] {
        guard sentence.count > maximumCharacters else { return [sentence] }

        var pieces: [String] = []
        var current = ""
        for clause in clauses(of: sentence) {
            if !current.isEmpty, current.count + clause.count > maximumCharacters {
                pieces.append(current)
                current = ""
            }
            current += clause
        }
        if !current.isEmpty { pieces.append(current) }

        return pieces
            .flatMap(breakAtSpaces)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }

    /// Keeps each comma, semicolon or colon with the clause before it, outside quotes.
    private static func clauses(of sentence: String) -> [String] {
        var result: [String] = []
        var current = ""
        var insideQuote = false
        for character in sentence {
            current.append(character)
            if quotes.contains(character) { insideQuote.toggle() }
            if !insideQuote, [",", ";", ":", "—"].contains(character) {
                result.append(current)
                current = ""
            }
        }
        if !current.isEmpty { result.append(current) }
        return result
    }

    private static func breakAtSpaces(_ text: String) -> [String] {
        guard text.count > maximumCharacters else { return [text] }

        var pieces: [String] = []
        var current = ""
        for word in text.split(separator: " ", omittingEmptySubsequences: true) {
            if !current.isEmpty, current.count + word.count + 1 > maximumCharacters {
                pieces.append(current)
                current = ""
            }
            current += current.isEmpty ? String(word) : " " + word
        }
        if !current.isEmpty { pieces.append(current) }
        return pieces
    }
}
