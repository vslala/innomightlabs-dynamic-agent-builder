import Foundation

/// Talks to the InnomightLabs agent over the Agent2Agent protocol.
///
/// A2A rather than the widget endpoints for two reasons. It authenticates with the agent API
/// key alone (`Authorization: Bearer pk_live_…`), where the widget conversation endpoints want
/// a visitor token obtained through a browser redirect. And `contextId` is a first-class
/// conversation key, so one recording maps to one durable conversation — the widget path
/// derives its conversation from WordPress-shaped `site_url`/`post_id` fields, which works but
/// couples Aura to a contract that has nothing to do with it.
///
/// Verified against the live agent: same `contextId` continues a conversation, and the reply
/// arrives at `result.task.status.message.parts[].text`.
struct InnomightLabsEditSuggester: EditSuggesting {
    /// The server rejects a message whose parts exceed this in total.
    static let maximumMessageCharacters = 32_000

    private let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    func suggest(instruction: String, context: EditSuggestionContext) async throws -> EditSuggestionResult {
        let trimmed = instruction.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw EditSuggestionError.emptyInstruction }

        let configuration = try AgentSettings.resolved()
        let prompt = EditSuggestionPrompt.build(
            instruction: trimmed,
            context: context,
            characterBudget: Self.maximumMessageCharacters
        )

        var request = URLRequest(url: configuration.messageEndpoint)
        request.httpMethod = "POST"
        request.timeoutInterval = 180
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(configuration.apiKey)", forHTTPHeaderField: "Authorization")
        request.httpBody = try Self.rpcBody(prompt: prompt, contextID: context.conversationKey)

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

        return EditSuggestionParser.parse(try Self.reply(in: data))
    }

    static func rpcBody(prompt: String, contextID: String) throws -> Data {
        // JSON-RPC 2.0. Note the method names are PascalCase (`SendMessage`) rather than the
        // A2A spec's `message/send`, and the role is the enum value `ROLE_USER`.
        let payload: [String: Any] = [
            "jsonrpc": "2.0",
            "id": UUID().uuidString,
            "method": "SendMessage",
            "params": [
                "message": [
                    "messageId": UUID().uuidString,
                    "role": "ROLE_USER",
                    "parts": [["kind": "text", "text": prompt]],
                    "contextId": contextID
                ],
                "configuration": ["acceptedOutputModes": ["text/plain"]]
            ]
        ]
        return try JSONSerialization.data(withJSONObject: payload)
    }

    // MARK: - Response

    private struct RPCEnvelope: Decodable {
        struct Failure: Decodable {
            let code: Int
            let message: String
        }

        struct Result: Decodable {
            let task: Task
        }

        struct Task: Decodable {
            let contextId: String?
            let status: Status
        }

        struct Status: Decodable {
            let state: String
            let message: Message?
        }

        struct Message: Decodable {
            let parts: [Part]
        }

        struct Part: Decodable {
            let text: String?
        }

        let result: Result?
        let error: Failure?
    }

    /// The agent's text, or a thrown error explaining why there isn't any.
    static func reply(in data: Data) throws -> String {
        let envelope = try? JSONDecoder().decode(RPCEnvelope.self, from: data)

        // JSON-RPC reports failures in the body with HTTP 200, so this is the real error path.
        if let failure = envelope?.error {
            throw EditSuggestionError.server(status: failure.code, detail: failure.message)
        }

        if let task = envelope?.result?.task {
            let text = (task.status.message?.parts ?? [])
                .compactMap(\.text)
                .joined()
                .trimmingCharacters(in: .whitespacesAndNewlines)

            if !text.isEmpty { return text }
            guard task.status.state == "TASK_STATE_COMPLETED" else {
                throw EditSuggestionError.server(
                    status: 0,
                    detail: "The agent finished in state \(task.status.state) without a reply."
                )
            }
        }

        // Fall back to scavenging any text part, so an unexpected task shape still yields
        // something rather than nothing.
        if let scavenged = textParts(in: data).first {
            return scavenged
        }
        throw EditSuggestionError.unreadableReply
    }

    /// FastAPI reports errors as `{"detail": "..."}` or `{"detail": [{"msg": "..."}]}`.
    static func detail(in data: Data) -> String {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return "" }
        if let detail = object["detail"] as? String { return detail }
        if let items = object["detail"] as? [[String: Any]] {
            return items.compactMap { $0["msg"] as? String }.joined(separator: "; ")
        }
        if let error = object["error"] as? [String: Any], let message = error["message"] as? String {
            return message
        }
        return ""
    }

    /// Every text part anywhere in the payload, longest first — the substantive reply is the
    /// long one. Used only as a fallback when the task shape isn't what we expect.
    static func textParts(in data: Data) -> [String] {
        guard let root = try? JSONSerialization.jsonObject(with: data) else { return [] }

        var found: [String] = []
        func walk(_ value: Any) {
            if let dictionary = value as? [String: Any] {
                if let text = dictionary["text"] as? String { found.append(text) }
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
