import Foundation

enum RecordingError: Error, Equatable, LocalizedError {
    case screenRecordingPermissionDenied
    case cameraPermissionDenied
    case microphonePermissionDenied
    case noShareableContentFound
    case writerSetupFailed(String)
    case captureStreamStopped(String)

    var errorDescription: String? {
        switch self {
        case .screenRecordingPermissionDenied:
            return "Screen Recording permission is required. Grant it in System Settings > Privacy & Security > Screen Recording, then relaunch Aura."
        case .cameraPermissionDenied:
            return "Camera permission is required. Grant it in System Settings > Privacy & Security > Camera."
        case .microphonePermissionDenied:
            return "Microphone permission is required. Grant it in System Settings > Privacy & Security > Microphone."
        case .noShareableContentFound:
            return "No recordable screens, windows, or apps were found."
        case .writerSetupFailed(let reason):
            return "Failed to set up recording: \(reason)"
        case .captureStreamStopped(let reason):
            return "Recording stopped unexpectedly: \(reason)"
        }
    }
}
