import Foundation

/// Remembers review-window display choices, so they survive reopening a session.
///
/// Same shape as `RecordingPreferences`: a caseless namespace over `UserDefaults` with
/// `Aura.`-prefixed keys.
enum ReviewPreferences {
    private static let waveformScaleKey = "Aura.waveformScale"

    static var waveformScale: WaveformScale {
        get {
            UserDefaults.standard.string(forKey: waveformScaleKey)
                .flatMap(WaveformScale.init(rawValue:)) ?? .decibel
        }
        set { UserDefaults.standard.set(newValue.rawValue, forKey: waveformScaleKey) }
    }
}
