import Foundation

/// Remembers review-window display choices, so they survive reopening a session.
///
/// Same shape as `RecordingPreferences`: a caseless namespace over `UserDefaults` with
/// `Aura.`-prefixed keys.
enum ReviewPreferences {
    private static let waveformScaleKey = "Aura.waveformScale"
    private static let followsPlayheadKey = "Aura.followsPlayhead"

    static var waveformScale: WaveformScale {
        get {
            UserDefaults.standard.string(forKey: waveformScaleKey)
                .flatMap(WaveformScale.init(rawValue:)) ?? .decibel
        }
        set { UserDefaults.standard.set(newValue.rawValue, forKey: waveformScaleKey) }
    }

    /// Whether the timeline scrolls to keep the playhead in view.
    ///
    /// Defaults to on. `UserDefaults` returns false for an absent bool, so the stored value is
    /// inverted — otherwise a first launch would read as "off" and the timeline would not
    /// follow until the user found the toggle.
    static var followsPlayhead: Bool {
        get { !UserDefaults.standard.bool(forKey: followsPlayheadKey) }
        set { UserDefaults.standard.set(!newValue, forKey: followsPlayheadKey) }
    }
}
