import Foundation

/// One proposed change, with the agent's reason for it.
///
/// Suggestions are never applied automatically. They land in a pending list and, when
/// accepted, go through the same `EditDocumentStore.apply` a mouse drag does — so the agent
/// has exactly the same powers as the user and no more, and every agent edit is undoable.
struct EditSuggestion: Identifiable, Equatable, Sendable {
    let id: UUID
    let operation: EditOperation
    let rationale: String?

    init(id: UUID = UUID(), operation: EditOperation, rationale: String? = nil) {
        self.id = id
        self.operation = operation
        self.rationale = rationale
    }
}

struct EditSuggestionResult: Equatable, Sendable {
    /// What the agent said, for the cases where it declined or asked a question.
    let reply: String
    let suggestions: [EditSuggestion]
    /// Things the agent asked Aura for rather than proposed. Answered locally and, where it
    /// needs another turn, followed up automatically.
    let requests: [AgentRequest]

    init(reply: String, suggestions: [EditSuggestion], requests: [AgentRequest] = []) {
        self.reply = reply
        self.suggestions = suggestions
        self.requests = requests
    }
}

/// The seam the review window talks to. `InnomightLabsEditSuggester` is the real
/// implementation; tests substitute their own.
protocol EditSuggesting: Sendable {
    func suggest(instruction: String, context: EditSuggestionContext) async throws -> EditSuggestionResult
}

/// Everything the agent needs to reason about the recording, gathered by the caller so the
/// suggester stays a pure transport. `markers` and `transcript` are retained alongside the
/// digest because the digest is a lossy, budget-trimmed view and callers sometimes need the
/// full thing.
struct EditSuggestionContext: Equatable, Sendable {
    let sessionID: String
    let duration: TimeInterval
    let transcript: Transcript?
    let document: SessionEdit
    let markers: [(time: TimeInterval, label: String)]
    /// The compact session digest the agent reasons from.
    let digest: SessionDigest?
    /// Set when this turn is Aura answering the agent's own `request_transcript`.
    var fulfilling: TimeSpan? = nil

    /// One durable conversation per recording. Deterministic from the session id, so it
    /// survives app restarts without anything being persisted.
    var conversationKey: String { "aura-session-\(sessionID)" }

    static func == (lhs: EditSuggestionContext, rhs: EditSuggestionContext) -> Bool {
        lhs.sessionID == rhs.sessionID
            && lhs.duration == rhs.duration
            && lhs.transcript == rhs.transcript
            && lhs.document == rhs.document
            && lhs.markers.map(\.time) == rhs.markers.map(\.time)
            && lhs.digest == rhs.digest
    }
}

enum EditSuggestionError: Error, Equatable, LocalizedError {
    case notConfigured
    case emptyInstruction
    case transport(String)
    case server(status: Int, detail: String)
    case unreadableReply

    var errorDescription: String? {
        switch self {
        case .notConfigured:
            return "Connect your InnomightLabs agent first (Agent Settings) to use AI edits."
        case .emptyInstruction:
            return "Type or dictate what you'd like changed."
        case .transport(let reason):
            return "Couldn't reach the InnomightLabs agent: \(reason)"
        case .server(let status, let detail):
            return detail.isEmpty ? "The agent returned an error (\(status))." : detail
        case .unreadableReply:
            return "The agent replied with something this build couldn't read."
        }
    }
}
