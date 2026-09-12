import SwiftUI

/// Colours shared across the review surfaces.
///
/// One token per meaning, defined once. "Cut regions on the waveform match the colour of a
/// struck-through word" is then true by construction rather than by two views happening to
/// pick the same red.
/// Every token resolves to an `AuraTheme` value, so the studio has one colour vocabulary
/// rather than two that drift.
enum ReviewPalette {
    /// Removed content — the shading on the waveform, the background behind a struck-through
    /// word, and the tint on a cut transcript line.
    static let cut = AuraTheme.danger

    /// A user-placed editorial marker.
    static let editorialMarker = AuraTheme.accent

    /// A marker logged during recording. Immutable, so it reads differently — dimmer rather
    /// than a second hue, since the palette is deliberately one accent.
    static let recordingMarker = AuraTheme.textSecondary

    /// An edit boundary that removes nothing.
    static let split = AuraTheme.textSecondary

    /// The current selection.
    static let selection = AuraTheme.accent

    /// The word currently being spoken.
    static let activeWord = AuraTheme.accent
}
