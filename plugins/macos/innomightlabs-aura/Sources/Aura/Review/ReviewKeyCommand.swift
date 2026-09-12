import Foundation

/// Keyboard commands in the studio window.
///
/// Resolved by one pure function and dispatched from a single event monitor, rather than by
/// scattering `.keyboardShortcut` across buttons. Four reasons that matters here: the window is
/// an `NSHostingView` in a bare `NSWindow` with no `commands` scene, so there is no menu to
/// hang shortcuts on; a shortcut attached to a conditionally-present button silently does not
/// exist while that button is hidden; an unmodified window-wide shortcut competes with the AI
/// prompt for ordinary keystrokes; and a single table is the only way the set stays
/// discoverable, since the command palette reads its shortcuts from the same vocabulary.
enum ReviewKeyCommand: Equatable, Sendable {
    case togglePlayback
    case cutSelection
    case clearSelection
    case splitAtPlayhead
    case armBlade
    case addMarker
    case markIn
    case markOut
    case undo
    case redo
    case zoomIn
    case zoomOut
    case zoomToFit
    case commandPalette
    case shuttle(ReviewShuttle)
    case nudgePlayhead(frames: Int)

    /// Where the keystroke is going, which decides whether it is a command at all.
    enum Focus: Equatable, Sendable {
        /// A text field has focus — ordinary characters belong to it.
        case textInput
        /// The timeline has focus.
        case timeline
    }

    struct Modifiers: OptionSet, Sendable {
        let rawValue: Int
        static let command = Modifiers(rawValue: 1 << 0)
        static let shift = Modifiers(rawValue: 1 << 1)
        static let option = Modifiers(rawValue: 1 << 2)
        static let control = Modifiers(rawValue: 1 << 3)
    }

    /// How far an arrow key moves the playhead. Frames rather than seconds so a nudge always
    /// lands on a frame boundary.
    static let smallSeekFrames = 1
    static let largeSeekFrames = 15

    /// Pure, so the whole key map is testable without a window.
    ///
    /// - Parameter characters: the event's characters, lowercased.
    static func resolve(
        characters: String,
        keyCode: UInt16,
        modifiers: Modifiers,
        focus: Focus
    ) -> ReviewKeyCommand? {
        // Most command-key chords are safe while typing; undo is the exception. A text field
        // owns Cmd+Z for its own editing, and taking it would undo a timeline edit while the
        // user was trying to undo a typo — with no way to get the text back.
        if modifiers.contains(.command) {
            switch characters {
            case "z" where focus == .textInput: return nil
            case "z" where modifiers.contains(.shift): return .redo
            case "z": return .undo
            case "k": return .commandPalette
            case "b": return .splitAtPlayhead
            case "=", "+": return .zoomIn
            case "-": return .zoomOut
            case "0": return .zoomToFit
            default: return nil
            }
        }

        // Escape is the one bare key that works everywhere: it is how you leave a palette or a
        // field, and it never inserts a character.
        if keyCode == 53 { return .clearSelection }

        guard focus == .timeline, !modifiers.contains(.control), !modifiers.contains(.option) else {
            return nil
        }

        switch keyCode {
        case 49: return .togglePlayback                 // space
        // Delete and Shift+Delete are the same ripple delete. Aura's timeline is derived from
        // cuts and cannot contain a gap, so "lift" — delete leaving a hole — is not
        // expressible. Mapping both to the ripple is truthful; adding a lift would mean a
        // second timeline model.
        case 51, 117: return .cutSelection              // delete, forward delete
        case 123: return .nudgePlayhead(frames: -seekFrames(modifiers))
        case 124: return .nudgePlayhead(frames: seekFrames(modifiers))
        default: break
        }

        switch characters {
        case "b": return .armBlade
        case "m": return .addMarker
        case "i": return .markIn
        case "o": return .markOut
        case "j": return .shuttle(.reverse)
        case "k": return .shuttle(.stop)
        case "l": return .shuttle(.forward)
        case "=", "+": return .zoomIn
        case "-", "_": return .zoomOut
        default: return nil
        }
    }

    private static func seekFrames(_ modifiers: Modifiers) -> Int {
        modifiers.contains(.shift) ? largeSeekFrames : smallSeekFrames
    }
}

/// J/K/L transport. A separate type so the key table does not depend on the view model.
enum ReviewShuttle: Equatable, Sendable {
    case reverse
    case stop
    case forward
}
