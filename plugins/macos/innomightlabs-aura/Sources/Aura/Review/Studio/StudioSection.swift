import Foundation

/// The left navigation's items.
///
/// Two of these are not built. They are listed — and visibly disabled — rather than omitted,
/// because the navigation is where a user looks to find out what the app can do; a missing item
/// reads as "this does not exist", while a dimmed one reads as "not yet". Neither should
/// dead-click.
enum StudioSection: String, CaseIterable, Identifiable, Sendable {
    case library
    case sessions
    case transcript
    case export
    case settings

    var id: String { rawValue }

    var title: String {
        switch self {
        case .library: return "Library"
        case .sessions: return "Sessions"
        case .transcript: return "Transcript"
        case .export: return "Export"
        case .settings: return "Settings"
        }
    }

    var symbol: String {
        switch self {
        case .library: return "square.grid.2x2"
        case .sessions: return "film.stack"
        case .transcript: return "text.alignleft"
        case .export: return "square.and.arrow.up"
        case .settings: return "gearshape"
        }
    }

    /// Settings is pinned to the bottom; the rest form the primary group.
    static var primary: [StudioSection] { [.library, .sessions, .transcript, .export] }

    var isAvailable: Bool {
        switch self {
        case .library, .sessions: return false
        case .transcript, .export, .settings: return true
        }
    }

    /// Shown as a tooltip on the unavailable items, so the dimming is explained rather than
    /// looking like a bug.
    var unavailableReason: String? {
        switch self {
        case .library: return "A media library isn't built yet — Aura edits one recording at a time."
        case .sessions: return "Browsing past recordings isn't built yet. They're in Movies › Aura."
        case .transcript, .export, .settings: return nil
        }
    }
}
