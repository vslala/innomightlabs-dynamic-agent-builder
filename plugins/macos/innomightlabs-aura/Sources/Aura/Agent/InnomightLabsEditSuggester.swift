import Foundation

/// Asks the InnomightLabs agent for edit suggestions over the Agent2Agent endpoint.
///
/// A2A rather than the widget endpoints because it is the only surface that authenticates
/// with the API key alone — the widget path additionally needs a visitor token obtained
/// through a browser redirect, which is a poor fit for a desktop app. It requires
/// Agent2Agent sharing to be enabled on the agent.
///
/// The reply is located defensively: A2A returns a task whose text can sit in the status
/// message, the history, or an artifact depending on how the agent answered, so rather than
/// assuming one shape this collects every text part it can find.
struct InnomightLabsEditSuggester: EditSuggesting {
    private let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    func suggest(instruction: String, context: EditSuggestionContext) async throws -> EditSuggestionResult {
        let trimmed = instruction.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw EditSuggestionError.emptyInstruction }

        guard
            AgentSettings.isConfigured,
            let agentID = AgentSettings.agentID,
            let apiKey = AgentSettings.apiKey,
            let url = URL(string: AgentSettings.baseURL)?
                .appendingPathComponent("a2a/agents/\(agentID)/message:send")
        else { throw EditSuggestionError.notConfigured }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.httpBody = try body(instruction: trimmed, context: context)

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw EditSuggestionError.transport(error.localizedDescription)
        }

        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw EditSuggestionError.server(status: http.statusCode, detail: Self.detail(in: data))
        }

        guard let reply = Self.textParts(in: data).first(where: { !$0.isEmpty }) else {
            throw EditSuggestionError.unreadableReply
        }
        return EditSuggestionParser.parse(reply)
    }

    private func body(instruction: String, context: EditSuggestionContext) throws -> Data {
        // A2A carries text parts only, so the whole briefing goes in one message.
        let payload: [String: Any] = [
            "message": [
                "messageId": UUID().uuidString,
                "role": "user",
                "parts": [["kind": "text", "text": EditSuggestionPrompt.build(instruction: instruction, context: context)]]
            ],
            "configuration": ["acceptedOutputModes": ["text/plain"]]
        ]
        return try JSONSerialization.data(withJSONObject: payload)
    }

    /// FastAPI reports errors as `{"detail": "..."}` or `{"detail": [{"msg": "..."}]}`.
    static func detail(in data: Data) -> String {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return "" }
        if let detail = object["detail"] as? String { return detail }
        if let items = object["detail"] as? [[String: Any]] {
            return items.compactMap { $0["msg"] as? String }.joined(separator: "; ")
        }
        return ""
    }

    /// Every `{"kind":"text","text":…}` in the response, deepest-last, so the agent's answer
    /// is found wherever the task put it. Longest first: the substantive reply is the long one.
    static func textParts(in data: Data) -> [String] {
        guard let root = try? JSONSerialization.jsonObject(with: data) else { return [] }

        var found: [String] = []
        func walk(_ value: Any) {
            if let dictionary = value as? [String: Any] {
                if dictionary["kind"] as? String == "text", let text = dictionary["text"] as? String {
                    found.append(text)
                }
                dictionary.values.forEach(walk)
            } else if let array = value as? [Any] {
                array.forEach(walk)
            }
        }
        walk(root)

        return found
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .sorted { $0.count > $1.count }
    }
}
