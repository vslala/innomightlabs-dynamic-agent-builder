import Foundation

/// One entry in the command palette.
///
/// `run` is deliberately not part of the value: the registry is a pure list so it can be
/// filtered and tested without a view model, and the action is looked up by `id` when the
/// command is actually invoked.
struct StudioCommand: Identifiable, Equatable, Sendable {
    enum Action: Equatable, Sendable {
        case studio(StudioAction)
        case splitAtPlayhead
        case deleteSelection
        case addMarker
        case layout(LayoutMode)
        case export
        case openTranscript
        case openAI
        case zoomIn
        case zoomOut
        case zoomToFit
        case toggleCaptions
        case armBlade
    }

    let id: String
    let title: String
    let subtitle: String?
    /// Extra words the search should match — synonyms and the vocabulary a user is likely to
    /// type instead of the title ("pauses" for "Remove silences").
    let keywords: [String]
    let shortcut: String?
    let action: Action

    init(
        id: String,
        title: String,
        subtitle: String? = nil,
        keywords: [String] = [],
        shortcut: String? = nil,
        action: Action
    ) {
        self.id = id
        self.title = title
        self.subtitle = subtitle
        self.keywords = keywords
        self.shortcut = shortcut
        self.action = action
    }
}

/// The palette's contents and its search.
///
/// Pure, so the whole registry is testable and the same list can back both the palette and any
/// future menu — and every row carries its shortcut, which is how the keyboard becomes
/// discoverable instead of something the user has to be told about.
enum CommandPalette {
    static let all: [StudioCommand] = [
        StudioCommand(
            id: "remove-silences",
            title: "Remove silences",
            subtitle: "Cut pauses longer than 0.35s",
            keywords: ["pauses", "gaps", "dead air", "quiet", "tighten"],
            action: .studio(.removeSilences)
        ),
        StudioCommand(
            id: "remove-fillers",
            title: "Remove filler words",
            subtitle: "Cut ums, uhs and ahs",
            keywords: ["um", "uh", "ah", "verbal tics", "clean up speech"],
            action: .studio(.removeFillerWords)
        ),
        StudioCommand(
            id: "generate-captions",
            title: "Generate captions",
            subtitle: "Subtitles from the transcript",
            keywords: ["subtitles", "srt", "vtt", "text"],
            action: .studio(.generateCaptions)
        ),
        StudioCommand(
            id: "create-highlights",
            title: "Create highlights",
            subtitle: "Ask the agent to mark key moments",
            keywords: ["key moments", "chapters", "best bits"],
            action: .studio(.createHighlights)
        ),
        StudioCommand(
            id: "shorten",
            title: "Shorten clip",
            subtitle: "Ask the agent for a shorter version",
            keywords: ["trim", "short", "condense", "60 second"],
            action: .studio(.shortenVideo)
        ),
        StudioCommand(
            id: "split",
            title: "Split at playhead",
            keywords: ["cut", "divide", "blade"],
            shortcut: "⌘B",
            action: .splitAtPlayhead
        ),
        StudioCommand(
            id: "blade",
            title: "Blade tool",
            subtitle: "Next click on the timeline splits there",
            keywords: ["razor", "cut", "scissors"],
            shortcut: "B",
            action: .armBlade
        ),
        StudioCommand(
            id: "delete-selection",
            title: "Delete selection",
            subtitle: "Ripple delete — the timeline closes the gap",
            keywords: ["remove", "ripple", "cut out"],
            shortcut: "⌫",
            action: .deleteSelection
        ),
        StudioCommand(
            id: "add-marker",
            title: "Add marker",
            keywords: ["bookmark", "note", "flag"],
            shortcut: "M",
            action: .addMarker
        ),
        StudioCommand(
            id: "layout-screen",
            title: "Screen only",
            subtitle: "Hide the camera from here on",
            keywords: ["layout", "camera off"],
            action: .layout(.screenOnly)
        ),
        StudioCommand(
            id: "layout-both",
            title: "Screen + camera",
            subtitle: "Camera as picture-in-picture",
            keywords: ["layout", "pip", "overlay"],
            action: .layout(.screenAndCamera)
        ),
        StudioCommand(
            id: "layout-camera",
            title: "Camera only",
            subtitle: "Camera fills the frame from here on",
            keywords: ["layout", "talking head", "full screen camera"],
            action: .layout(.cameraOnly)
        ),
        StudioCommand(
            id: "toggle-captions",
            title: "Toggle captions",
            subtitle: "Show or hide subtitles and the captions lane",
            keywords: ["subtitles", "cc"],
            action: .toggleCaptions
        ),
        StudioCommand(
            id: "zoom-in",
            title: "Zoom in",
            keywords: ["timeline", "closer"],
            shortcut: "+",
            action: .zoomIn
        ),
        StudioCommand(
            id: "zoom-out",
            title: "Zoom out",
            keywords: ["timeline", "wider"],
            shortcut: "−",
            action: .zoomOut
        ),
        StudioCommand(
            id: "zoom-fit",
            title: "Fit timeline",
            subtitle: "Show the whole recording",
            keywords: ["zoom", "whole", "all"],
            shortcut: "⌘0",
            action: .zoomToFit
        ),
        StudioCommand(
            id: "open-transcript",
            title: "Open transcript",
            keywords: ["text", "words", "panel"],
            action: .openTranscript
        ),
        StudioCommand(
            id: "open-ai",
            title: "Ask Aura",
            subtitle: "Open the AI copilot",
            keywords: ["agent", "ai", "copilot", "chat"],
            action: .openAI
        ),
        StudioCommand(
            id: "export",
            title: "Export…",
            subtitle: "Render the edited video",
            keywords: ["save", "render", "share", "mp4"],
            action: .export
        ),
    ]

    /// Ranked search over titles, keywords and subtitles.
    ///
    /// Subsequence matching is what a palette user expects — "rmsil" should find "Remove
    /// silences" — but a scattered subsequence must not outrank an exact hit. Without tiering,
    /// typing "srt" found "Shorten clip" (s·h·o·**r**·**t**) ahead of "Generate captions",
    /// whose keywords literally contain "srt". So exactness dominates, and only within a tier
    /// does an earlier match win.
    static func matching(_ query: String, in commands: [StudioCommand] = all) -> [StudioCommand] {
        let needle = query.trimmingCharacters(in: .whitespaces).lowercased()
        guard !needle.isEmpty else { return commands }

        return commands
            .compactMap { command -> (StudioCommand, Int)? in
                score(needle, for: command).map { (command, $0) }
            }
            .sorted { $0.1 < $1.1 }
            .map(\.0)
    }

    /// Tier bases, an order of magnitude apart so a position offset can never cross a tier.
    private enum Tier {
        static let titleExact = 0
        static let titlePrefix = 1_000
        static let keywordExact = 2_000
        static let keywordPrefix = 3_000
        static let titleSubsequence = 4_000
        static let keywordSubsequence = 5_000
        static let subtitleSubsequence = 6_000
    }

    private static func score(_ needle: String, for command: StudioCommand) -> Int? {
        let title = command.title.lowercased()
        let keywords = command.keywords.map { $0.lowercased() }

        if title == needle { return Tier.titleExact }
        if keywords.contains(needle) { return Tier.keywordExact }
        if title.hasPrefix(needle) { return Tier.titlePrefix }
        if keywords.contains(where: { $0.hasPrefix(needle) }) { return Tier.keywordPrefix }

        if let position = matchScore(needle, in: title) {
            return Tier.titleSubsequence + position
        }
        if let position = keywords.compactMap({ matchScore(needle, in: $0) }).min() {
            return Tier.keywordSubsequence + position
        }
        if let subtitle = command.subtitle?.lowercased(),
           let position = matchScore(needle, in: subtitle) {
            return Tier.subtitleSubsequence + position
        }
        return nil
    }

    /// Nil when `needle` is not a subsequence of `haystack`; otherwise the index the match
    /// started at, so earlier matches rank better.
    private static func matchScore(_ needle: String, in haystack: String) -> Int? {
        var start: Int?
        var index = haystack.startIndex
        var position = 0

        for character in needle {
            guard let found = haystack[index...].firstIndex(of: character) else { return nil }
            position += haystack.distance(from: index, to: found)
            if start == nil { start = position }
            index = haystack.index(after: found)
            position += 1
        }
        return start
    }
}
