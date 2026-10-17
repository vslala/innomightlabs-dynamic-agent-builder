import Foundation

/// Choices the user makes once about Speech Replacement and expects to be remembered.
enum SpeechPreferences {
    private static let cameraWarningKey = "Aura.speechReplacementSuppressCameraWarning"

    /// True once the user has said not to warn them that the camera is visible where new words
    /// are being spoken. Reset from Settings.
    static var suppressesCameraWarning: Bool {
        get { UserDefaults.standard.bool(forKey: cameraWarningKey) }
        set { UserDefaults.standard.set(newValue, forKey: cameraWarningKey) }
    }
}
