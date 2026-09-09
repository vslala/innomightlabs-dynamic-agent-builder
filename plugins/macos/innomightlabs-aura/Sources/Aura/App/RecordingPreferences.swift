import Foundation

/// Remembers the last-picked capture target/camera by display name, so the picker
/// defaults are restored on next launch. Names are matched against whatever is
/// currently available; no match just falls back to no selection.
enum RecordingPreferences {
    private static let captureTargetNameKey = "Aura.lastCaptureTargetName"
    private static let cameraNameKey = "Aura.lastCameraName"

    static var lastCaptureTargetName: String? {
        get { UserDefaults.standard.string(forKey: captureTargetNameKey) }
        set { UserDefaults.standard.set(newValue, forKey: captureTargetNameKey) }
    }

    static var lastCameraName: String? {
        get { UserDefaults.standard.string(forKey: cameraNameKey) }
        set { UserDefaults.standard.set(newValue, forKey: cameraNameKey) }
    }
}
