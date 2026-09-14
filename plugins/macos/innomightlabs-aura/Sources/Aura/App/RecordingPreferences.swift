import Foundation

/// Remembers the last-picked capture target/camera/microphone by display name, and the last
/// recording profile, so the menu bar's defaults are restored on next launch. Device names are
/// matched against whatever is currently available; no match just falls back to no selection.
enum RecordingPreferences {
    private static let captureTargetNameKey = "Aura.lastCaptureTargetName"
    private static let cameraNameKey = "Aura.lastCameraName"
    private static let microphoneNameKey = "Aura.lastMicrophoneName"
    private static let profileKey = "Aura.lastRecordingProfile"

    static var lastCaptureTargetName: String? {
        get { UserDefaults.standard.string(forKey: captureTargetNameKey) }
        set { UserDefaults.standard.set(newValue, forKey: captureTargetNameKey) }
    }

    static var lastCameraName: String? {
        get { UserDefaults.standard.string(forKey: cameraNameKey) }
        set { UserDefaults.standard.set(newValue, forKey: cameraNameKey) }
    }

    static var lastMicrophoneName: String? {
        get { UserDefaults.standard.string(forKey: microphoneNameKey) }
        set { UserDefaults.standard.set(newValue, forKey: microphoneNameKey) }
    }

    /// JSON-encoded, unlike the name-based preferences above: a profile is an exact value
    /// (which tracks are on), not something to fuzzy-match against what is currently
    /// available. A decode failure — an old build's shape, or no value yet — falls back to
    /// `nil`, which `RecordingSetupViewModel` reads as "use Full Studio".
    static var lastProfile: RecordingProfile? {
        get {
            guard let data = UserDefaults.standard.data(forKey: profileKey) else { return nil }
            return try? JSONDecoder().decode(RecordingProfile.self, from: data)
        }
        set {
            guard let newValue, let data = try? JSONEncoder().encode(newValue) else {
                UserDefaults.standard.removeObject(forKey: profileKey)
                return
            }
            UserDefaults.standard.set(data, forKey: profileKey)
        }
    }
}
