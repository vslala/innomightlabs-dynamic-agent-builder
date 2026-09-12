import Foundation

/// The suggested actions in the AI panel.
///
/// Each one maps to something that actually changes the editor. That mapping is the point of
/// the panel: an action that produced prose describing an edit, rather than performing it,
/// would be a chatbot bolted to a timeline.
///
/// `kind` is explicit so an action with no implementation is visibly unavailable rather than a
/// button that silently does nothing.
enum StudioAction: String, CaseIterable, Identifiable, Sendable {
    case removeSilences
    case removeFillerWords
    case generateCaptions
    case createHighlights
    case shortenVideo
    case cleanAudio

    var id: String { rawValue }

    var title: String {
        switch self {
        case .removeSilences: return "Remove silences"
        case .removeFillerWords: return "Remove filler words"
        case .generateCaptions: return "Generate captions"
        case .createHighlights: return "Create highlights"
        case .shortenVideo: return "Shorten clip"
        case .cleanAudio: return "Clean audio"
        }
    }

    var subtitle: String {
        switch self {
        case .removeSilences: return "Cut long pauses"
        case .removeFillerWords: return "Cut ums and ahs"
        case .generateCaptions: return "Subtitles from the transcript"
        case .createHighlights: return "Find key moments"
        case .shortenVideo: return "Turn this into a short version"
        case .cleanAudio: return "Noise reduction — not built yet"
        }
    }

    var symbol: String {
        switch self {
        case .removeSilences: return "waveform.path"
        case .removeFillerWords: return "text.badge.minus"
        case .generateCaptions: return "captions.bubble"
        case .createHighlights: return "sparkle.magnifyingglass"
        case .shortenVideo: return "scissors"
        case .cleanAudio: return "waveform.badge.exclamationmark"
        }
    }

    /// How the action is carried out.
    enum Kind: Equatable, Sendable {
        /// Computed here, deterministically, as one undoable operation.
        case local
        /// Sent to the agent as a crafted instruction.
        case agent(prompt: String)
        /// No implementation. Shown, disabled, with the reason.
        case unavailable(reason: String)
    }

    var kind: Kind {
        switch self {
        case .removeSilences, .removeFillerWords, .generateCaptions:
            return .local

        case .createHighlights:
            return .agent(prompt: """
            Find the three or four most useful moments in this recording and mark each one \
            with add_marker, naming it after what happens there. Do not cut anything.
            """)

        case .shortenVideo:
            return .agent(prompt: """
            Shorten this recording to roughly a third of its length while keeping it coherent. \
            Cut whole passages that repeat, digress, or add nothing, using remove_range, and \
            explain each cut in its "why".
            """)

        case .cleanAudio:
            return .unavailable(reason: """
            Noise reduction isn't implemented yet. You can mute or level a lane from its name \
            in the timeline.
            """)
        }
    }
}
