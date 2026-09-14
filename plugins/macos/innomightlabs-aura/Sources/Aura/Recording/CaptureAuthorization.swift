import AVFoundation

/// Shared by the `AVCaptureDevice`-backed sources — camera and microphone. Screen Recording has
/// no pre-flight authorization API, so `ScreenCaptureSource` has no counterpart to this: a
/// denied or not-yet-granted state there surfaces as `SCShareableContent.current` throwing in
/// the picker, or `SCStream.startCapture()` throwing.
enum CaptureAuthorization {
    static func request(_ media: AVMediaType, denied: RecordingError) async throws {
        switch AVCaptureDevice.authorizationStatus(for: media) {
        case .authorized:
            return
        case .notDetermined:
            guard await AVCaptureDevice.requestAccess(for: media) else { throw denied }
        default:
            throw denied
        }
    }
}
