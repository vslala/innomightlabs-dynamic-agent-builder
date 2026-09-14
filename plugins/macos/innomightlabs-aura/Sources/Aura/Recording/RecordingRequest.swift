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

    /// The same request with a different profile. `RecordingController.switchProfile` uses
    /// this to turn "what the session started with" into "what it should record now" without
    /// asking the caller to resupply the screen target or device ids, which never change.
    func replacing(profile: RecordingProfile) -> RecordingRequest {
        RecordingRequest(
            profile: profile,
            screenTarget: screenTarget,
            cameraDeviceID: cameraDeviceID,
            microphoneDeviceID: microphoneDeviceID
        )
    }
}
