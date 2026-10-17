import Foundation

/// Runtime switches for features with explicit availability or privacy costs.
///
/// Read from `UserDefaults`, so a flag can be flipped without a rebuild:
///
///     defaults write com.innomightlabs.aura Aura.wakeWordListenerEnabled -bool YES
enum FeatureFlags {
    private static let wakeWordListenerKey = "Aura.wakeWordListenerEnabled"

    /// Available by default; downloads still require consent, and Chrome is controlled only
    /// after the user starts a demo. An explicit false preference disables the feature.
    static var isBrowserDemoEnabled: Bool {
        get {
            UserDefaults.standard.object(forKey: "Aura.browserDemoEnabled") == nil
                || UserDefaults.standard.bool(forKey: "Aura.browserDemoEnabled")
        }
        set { UserDefaults.standard.set(newValue, forKey: "Aura.browserDemoEnabled") }
    }

    /// Always-on "Hey Mycroft" detection.
    ///
    /// Off by default and deliberately so: it holds the microphone open for the entire life
    /// of the app, which is both a privacy cost the user hasn't asked for and a surprising
    /// amount of complexity for what it currently does (log a detection). Nothing downstream
    /// consumes a detection yet, so there is no benefit on the other side of that cost.
    /// While this is off, Aura only touches the microphone during a recording.
    static var isWakeWordListenerEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: wakeWordListenerKey) }
        set { UserDefaults.standard.set(newValue, forKey: wakeWordListenerKey) }
    }
}
