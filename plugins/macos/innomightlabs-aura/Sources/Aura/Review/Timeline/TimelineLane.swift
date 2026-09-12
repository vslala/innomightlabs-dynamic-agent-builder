import Foundation

/// The two video sources, named as the user thinks of them.
enum VideoLane: String, CaseIterable, Sendable {
    case screen
    case camera
}

/// One row of the timeline.
///
/// Aura recorded the session, so the lane set is known rather than discovered: there is exactly
/// one screen, one camera, one microphone and one system-audio track, plus captions derived
/// from the transcript. That is why these are named Screen and Voice rather than "Video 1" and
/// "Audio 1" — a generic track list would be pretending not to know what it recorded.
enum TimelineLane: String, CaseIterable, Identifiable, Sendable {
    case captions
    case screen
    case camera
    case voice
    case systemAudio

    var id: String { rawValue }

    var title: String {
        switch self {
        case .captions: return "Captions"
        case .screen: return "Screen"
        case .camera: return "Camera"
        case .voice: return "Voice"
        case .systemAudio: return "System Audio"
        }
    }

    var symbol: String {
        switch self {
        case .captions: return "captions.bubble"
        case .screen: return "display"
        case .camera: return "camera"
        case .voice: return "mic"
        case .systemAudio: return "speaker.wave.2"
        }
    }

    var height: CGFloat {
        switch self {
        case .captions: return 32
        case .screen: return 44
        case .camera: return 40
        case .voice, .systemAudio: return 44
        }
    }

    var audioLane: AudioLane? {
        switch self {
        case .voice: return .microphone
        case .systemAudio: return .systemAudio
        case .captions, .screen, .camera: return nil
        }
    }

    var videoLane: VideoLane? {
        switch self {
        case .screen: return .screen
        case .camera: return .camera
        case .captions, .voice, .systemAudio: return nil
        }
    }
}
