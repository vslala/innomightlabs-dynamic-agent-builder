import Foundation

/// Pulls operations out of the agent's reply.
///
/// Pure and defensively written, because the reply is free text from a language model: the
/// JSON may be fenced, bare, wrapped in an object, or absent entirely. Anything that doesn't
/// parse into a known operation is dropped rather than guessed at — a suggestion the user
/// can't trust is worse than no suggestion.
enum EditSuggestionParser {
    private struct Rationale: Decodable {
        let why: String?
    }

    private struct Wrapper: Decodable {
        let operations: [JSONValueBox]
    }

    /// Keeps each operation's raw JSON so it can be decoded twice — once as an operation and
    /// once for its `why` — without the two decodings having to agree on one type.
    private struct JSONValueBox: Decodable {
        let data: Data

        init(from decoder: Decoder) throws {
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(AnyCodable.self)
            data = try JSONSerialization.data(withJSONObject: raw.value)
        }
    }

    private struct AnyCodable: Decodable {
        let value: Any

        init(from decoder: Decoder) throws {
            let container = try decoder.singleValueContainer()
            if let dictionary = try? container.decode([String: AnyCodable].self) {
                value = dictionary.mapValues(\.value)
            } else if let array = try? container.decode([AnyCodable].self) {
                value = array.map(\.value)
            } else if let bool = try? container.decode(Bool.self) {
                value = bool
            } else if let number = try? container.decode(Double.self) {
                value = number
            } else if let string = try? container.decode(String.self) {
                value = string
            } else {
                value = NSNull()
            }
        }
    }

    static func parse(_ reply: String) -> EditSuggestionResult {
        guard let json = extractJSON(from: reply) else {
            return EditSuggestionResult(
                reply: reply.trimmingCharacters(in: .whitespacesAndNewlines),
                suggestions: [],
                requests: []
            )
        }

        var suggestions: [EditSuggestion] = []
        var requests: [AgentRequest] = []

        for box in decodeBoxes(json.payload) {
            // Requests first: they share the `op` field but are not applicable edits.
            if let object = try? JSONSerialization.jsonObject(with: box.data) as? [String: Any],
               let request = AgentRequest.from(json: object) {
                requests.append(request)
                continue
            }
            guard let operation = try? JSONDecoder().decode(EditOperation.self, from: box.data) else { continue }
            let why = (try? JSONDecoder().decode(Rationale.self, from: box.data))?.why
            suggestions.append(EditSuggestion(operation: operation, rationale: why?.isEmpty == false ? why : nil))
        }

        return EditSuggestionResult(reply: json.prose, suggestions: suggestions, requests: requests)
    }

    private static func decodeBoxes(_ data: Data) -> [JSONValueBox] {
        let decoder = JSONDecoder()
        if let array = try? decoder.decode([JSONValueBox].self, from: data) {
            return array
        }
        // Also accept `{"operations": [...]}`, which models produce about as often.
        if let wrapper = try? decoder.decode(Wrapper.self, from: data) {
            return wrapper.operations
        }
        // And a single bare operation object.
        if let single = try? decoder.decode(JSONValueBox.self, from: data) {
            return [single]
        }
        return []
    }

    /// Finds the JSON payload and the prose around it.
    private static func extractJSON(from reply: String) -> (payload: Data, prose: String)? {
        if let fenced = fencedBlock(in: reply) {
            let prose = reply
                .replacingOccurrences(of: fenced.block, with: "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return (Data(fenced.body.utf8), prose)
        }

        guard let span = balancedSpan(in: reply) else { return nil }
        let prose = (String(reply[reply.startIndex..<span.lowerBound])
            + String(reply[span.upperBound...]))
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return (Data(reply[span].utf8), prose)
    }

    private static func fencedBlock(in reply: String) -> (block: String, body: String)? {
        for marker in ["```json", "```JSON", "```"] {
            guard let start = reply.range(of: marker) else { continue }
            let afterMarker = start.upperBound
            guard let end = reply.range(of: "```", range: afterMarker..<reply.endIndex) else { continue }
            let body = String(reply[afterMarker..<end.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
            guard !body.isEmpty else { continue }
            return (String(reply[start.lowerBound..<end.upperBound]), body)
        }
        return nil
    }

    /// The first balanced `[...]` or `{...}`, ignoring brackets inside strings.
    private static func balancedSpan(in reply: String) -> Range<String.Index>? {
        guard let start = reply.firstIndex(where: { $0 == "[" || $0 == "{" }) else { return nil }
        let open = reply[start]
        let close: Character = open == "[" ? "]" : "}"

        var depth = 0
        var inString = false
        var escaped = false
        var index = start

        while index < reply.endIndex {
            let character = reply[index]
            if escaped {
                escaped = false
            } else if character == "\\" {
                escaped = true
            } else if character == "\"" {
                inString.toggle()
            } else if !inString {
                if character == open {
                    depth += 1
                } else if character == close {
                    depth -= 1
                    if depth == 0 {
                        return start..<reply.index(after: index)
                    }
                }
            }
            index = reply.index(after: index)
        }
        return nil
    }
}
