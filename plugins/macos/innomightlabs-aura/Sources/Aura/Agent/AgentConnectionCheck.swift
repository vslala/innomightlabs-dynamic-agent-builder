import Foundation

/// Verifies the agent settings actually work, and discovers what it can.
///
/// Three steps because they answer different questions. `/widget/config` needs only the public
/// key, so it proves the key is valid *and* returns the agent id — meaning the user can paste a
/// key and have the id filled in. The A2A card then confirms Agent2Agent is enabled on that
/// agent, which is invisible from the key alone. Last, one authenticated A2A call proves the
/// client secret works: the first two pass without it, so skipping this would report a
/// connection that fails on the first edit.
enum AgentConnectionCheck {
    struct Outcome: Equatable {
        let agentName: String?
        let agentID: String?
        let isA2AEnabled: Bool
        let message: String
        let isUsable: Bool
    }

    static func run(
        baseURL: String,
        agentID: String?,
        apiKey: String,
        a2aSecret: String,
        session: URLSession = .shared
    ) async -> Outcome {
        guard let base = URL(string: baseURL), base.scheme != nil else {
            return Outcome(agentName: nil, agentID: nil, isA2AEnabled: false,
                           message: "That base URL isn't valid.", isUsable: false)
        }
        guard !apiKey.isEmpty else {
            return Outcome(agentName: nil, agentID: nil, isA2AEnabled: false,
                           message: "Paste your agent API key.", isUsable: false)
        }
        guard !a2aSecret.isEmpty else {
            return Outcome(agentName: nil, agentID: nil, isA2AEnabled: false,
                           message: "Paste the key's A2A client secret.", isUsable: false)
        }
        // The dashboard's "Secret keys" (`sk_live_…`) are for the /v1 Public API and look like
        // the right thing to paste here, but A2A rejects them.
        guard !a2aSecret.hasPrefix("sk_live_") else {
            return Outcome(
                agentName: nil, agentID: nil, isA2AEnabled: false,
                message: "That's a Public API secret key (sk_live_…). Aura needs the A2A client secret (a2a_live_…) generated on the API key.",
                isUsable: false
            )
        }

        let discovered = await discover(base: base, apiKey: apiKey, session: session)
        guard let resolvedID = discovered?.id ?? agentID.flatMap({ $0.isEmpty ? nil : $0 }) else {
            return Outcome(agentName: nil, agentID: nil, isA2AEnabled: false,
                           message: "The key was rejected, or no agent is associated with it.", isUsable: false)
        }

        let card = await cardName(base: base, agentID: resolvedID, session: session)
        guard let card else {
            return Outcome(
                agentName: discovered?.name,
                agentID: resolvedID,
                isA2AEnabled: false,
                message: "Key works, but Agent2Agent sharing is off for this agent — enable it in the dashboard.",
                isUsable: false
            )
        }

        guard await secretIsAccepted(base: base, agentID: resolvedID, secret: a2aSecret, session: session) else {
            return Outcome(
                agentName: card,
                agentID: resolvedID,
                isA2AEnabled: true,
                message: "The A2A client secret was rejected. Generate or rotate it on the key in the dashboard.",
                isUsable: false
            )
        }

        return Outcome(
            agentName: card,
            agentID: resolvedID,
            isA2AEnabled: true,
            message: "Connected to “\(card)”.",
            isUsable: true
        )
    }

    private static func discover(base: URL, apiKey: String, session: URLSession) async -> (id: String, name: String?)? {
        var request = URLRequest(url: base.appendingPathComponent("widget/config"))
        request.timeoutInterval = 30
        request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")

        guard
            let (data, response) = try? await session.data(for: request),
            let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode),
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let id = object["agent_id"] as? String
        else { return nil }
        return (id, object["agent_name"] as? String)
    }

    /// The A2A card is unauthenticated but only exists when sharing is enabled, so its
    /// presence is the check.
    private static func cardName(base: URL, agentID: String, session: URLSession) async -> String? {
        var request = URLRequest(url: base.appendingPathComponent("a2a/agents/\(agentID)/card"))
        request.timeoutInterval = 30

        guard
            let (data, response) = try? await session.data(for: request),
            let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode),
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return (object["name"] as? String) ?? agentID
    }

    /// `ListTasks` is the cheapest authenticated call: it reads, starts nothing, and a wrong
    /// secret comes back as HTTP 401.
    private static func secretIsAccepted(base: URL, agentID: String, secret: String, session: URLSession) async -> Bool {
        let payload: [String: Any] = ["jsonrpc": "2.0", "id": UUID().uuidString, "method": "ListTasks", "params": [:]]
        guard let body = try? JSONSerialization.data(withJSONObject: payload) else { return false }
        let request = InnomightLabsEditSuggester.request(
            to: base.appendingPathComponent("a2a/agents/\(agentID)"),
            secret: secret,
            body: body,
            timeout: 30
        )

        guard
            let (data, response) = try? await session.data(for: request),
            let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode),
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return false }
        return object["error"] == nil
    }
}
