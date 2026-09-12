import Foundation

/// Keyboard commands in the review window.
///
/// Resolved by one pure function and dispatched from a single event monitor, rather than by
/// scattering `.keyboardShortcut` across buttons. Three reasons that matters here: the window
/// is an `NSHostingView` in a bare `NSWindow` with no `commands` scene, so there is no menu to
/// hang shortcuts on; a shortcut attached to a conditionally-present button silently does not
/// exist while that button is hidden; and an unmodified window-wide shortcut competes with the
/// agent panel's text field for ordinary keystrokes.
enum ReviewKeyCommand: Equatable, Sendable {
    case togglePlayback
    case cutSelection
    case clearSelection
    case splitAtPlayhead
    case addMarker
    case undo
    case redo
    case zoomIn
    case zoomOut
    case zoomToFit
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
            case "=", "+": return .zoomIn
            case "-": return .zoomOut
            case "0": return .zoomToFit
            default: return nil
            }
        }

        guard focus == .timeline, !modifiers.contains(.control), !modifiers.contains(.option) else {
            return nil
        }

        switch keyCode {
        case 49: return .togglePlayback                 // space
        case 51, 117: return .cutSelection              // delete, forward delete
        case 53: return .clearSelection                 // escape
        case 123: return .nudgePlayhead(frames: modifiers.contains(.shift) ? -10 : -1)
        case 124: return .nudgePlayhead(frames: modifiers.contains(.shift) ? 10 : 1)
        default: break
        }

        switch characters {
        case "s": return .splitAtPlayhead
        case "m": return .addMarker
        default: return nil
        }
    }
}
