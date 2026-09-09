import CoreMedia

/// Adapts `ScreenCaptureSession`'s system-audio callback into `system-audio.m4a`'s `TrackWriter`.
final class SystemAudioSink: @unchecked Sendable {
    private let trackWriter: TrackWriter

    init(trackWriter: TrackWriter) {
        self.trackWriter = trackWriter
    }

    func handle(_ sampleBuffer: CMSampleBuffer) {
        trackWriter.append(sampleBuffer)
    }
}
