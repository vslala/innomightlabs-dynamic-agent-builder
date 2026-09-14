import Foundation

/// Turns a request into the sources that will record it.
///
/// The single site where "is this source enabled" is asked. Everything downstream iterates the
/// returned list, which is why `RecordingController` has no per-source branches.
enum CaptureSourceFactory {
    static func sources(for request: RecordingRequest) -> [any CaptureSource] {
        var sources: [any CaptureSource] = []

        // One source for both, because one `SCStream` produces both. See `ScreenCaptureSource`.
        let screenKinds = request.profile.screenCaptureKinds
        if !screenKinds.isEmpty, let target = request.screenTarget {
            sources.append(ScreenCaptureSource(target: target, kinds: screenKinds))
        }
        if request.profile.tracks.contains(.camera) {
            sources.append(CameraCaptureSource(
                deviceID: request.cameraDeviceID,
                quality: CameraQuality(profile: request.profile)
            ))
        }
        if request.profile.tracks.contains(.microphone) {
            sources.append(MicrophoneCaptureSource(deviceID: request.microphoneDeviceID))
        }

        return sources
    }
}
