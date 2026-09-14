import Foundation

/// What the user asked to record, with the profile/target agreement checked in one pure place.
/// `CaptureSourceFactory` turns this into capture sources; nothing downstream reads it.
struct RecordingRequest: Sendable {
    var profile: RecordingProfile
    /// The `SCStream` content filter source. Required whenever the profile needs a stream —
    /// including system-audio-without-screen, where ScreenCaptureKit still requires a filter
    /// even though no `.screen` output is attached. The picker supplies the primary display in
    /// that case, so neither the factory nor the source has a special case.
    var screenTarget: CaptureTarget?
    var cameraDeviceID: String?
    var microphoneDeviceID: String?

    var isValid: Bool {
        guard profile.isRecordable else { return false }
        if profile.needsScreenCaptureStream && screenTarget == nil { return false }
        return true
    }
}
