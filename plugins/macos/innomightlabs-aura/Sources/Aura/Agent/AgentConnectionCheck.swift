import Foundation

/// Verifies the agent settings actually work, and discovers what it can.
///
/// Two steps because they answer different questions. `/widget/config` needs only the API key,
/// so it proves the key is valid *and* returns the agent id — meaning the user can paste a key
/// and have the rest filled in. The A2A card then confirms Agent2Agent is enabled on that
/// agent, which is the part that actually has to be true for editing to work, and is invisible
/// from the key alone.
enum AgentConnectionCheck {
    struct Outcome: Equatable {
        let agentName: String?
        let agentID: String?
        let isA2AEnabled: Bool
        let message: String
        let isUsable: Bool
    }

    static func run(baseURL: String, agentID: String?, apiKey: String, session: URLSession = .shared) async -> Outcome {
        guard let base = URL(string: baseURL), base.scheme != nil else {
            return Outcome(agentName: nil, agentID: nil, isA2AEnabled: false,
                           message: "That base URL isn't valid.", isUsable: false)
        }
        guard !apiKey.isEmpty else {
            return Outcome(agentName: nil, agentID: nil, isA2AEnabled: false,
                           message: "Paste your agent API key.", isUsable: false)
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
}
