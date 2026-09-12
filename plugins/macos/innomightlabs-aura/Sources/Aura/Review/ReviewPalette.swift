import SwiftUI

/// Colours shared across the review surfaces.
///
/// One token per meaning, defined once. "Cut regions on the waveform match the colour of a
/// struck-through word" is then true by construction rather than by two views happening to
/// pick the same red.
enum ReviewPalette {
    /// Removed content — the shading on the waveform, the background behind a struck-through
    /// word, and the tint on a cut transcript line.
    static let cut = Color.red

    /// A user-placed editorial marker.
    static let editorialMarker = Color.yellow

    /// A marker logged during recording. Immutable, so it reads differently.
    static let recordingMarker = Color.orange

    /// An edit boundary that removes nothing.
    static let split = Color.secondary

    /// The current selection.
    static let selection = Color.accentColor

    /// The word currently being spoken.
    static let activeWord = Color.accentColor
}
