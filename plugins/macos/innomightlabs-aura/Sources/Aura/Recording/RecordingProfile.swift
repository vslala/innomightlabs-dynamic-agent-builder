import Foundation

/// Which sources a recording captures.
///
/// A set, not four flags: the recorder builds one `CaptureSource` per enabled kind and fans the
/// lifecycle over the list, and the menu bar renders one toggle row per `TrackKind.allCases`.
/// Both are collection operations, and neither has a branch per source.
struct RecordingProfile: Equatable, Codable, Sendable {
    var tracks: Set<TrackKind>

    static let fullStudio = RecordingProfile(tracks: Set(TrackKind.allCases))

    /// Nothing selected is not a recording. The Start button is disabled on this, and
    /// `RecordingController.start` guards on it too — a disabled button is a UI state, not an
    /// invariant.
    var isRecordable: Bool { !tracks.isEmpty }

    /// Always derived through `allCases`, never by iterating the set: a `Set` has no order, and
    /// writer creation, teardown and the `track_start` events must be deterministic.
    var enabledKinds: [TrackKind] { TrackKind.allCases.filter(tracks.contains) }

    var hasVideo: Bool { enabledKinds.contains { $0.isVideo } }
    var isAudioOnly: Bool { isRecordable && !hasVideo }

    /// The kinds `SCStream` is responsible for. Non-empty means one `ScreenCaptureSource`.
    var screenCaptureKinds: Set<TrackKind> {
        tracks.intersection(ScreenCaptureSource.supportedKinds)
    }

    /// System audio is captured *through* ScreenCaptureKit, so it needs the same TCC grant and
    /// the same stream as screen video — which is why an audio-only podcast that wants a remote
    /// guest still triggers the Screen Recording prompt.
    var needsScreenCaptureStream: Bool { !screenCaptureKinds.isEmpty }

    /// A compact label for the `record_start` event — e.g. `"screen+microphone"`.
    var eventLabel: String {
        enabledKinds.map(\.rawValue).joined(separator: "+")
    }

    init(tracks: Set<TrackKind>) {
        self.tracks = tracks
    }
}

/// The named modes in the menu bar. A preset is a shortcut that *writes* a profile; the
/// profile remains the source of truth, and a profile matching no preset is "Custom".
enum RecordingPreset: String, CaseIterable, Identifiable, Sendable {
    case fullStudio
    case screenAndVoice
    case screenAndSystemAudio
    case podcast
    case cameraOnly

    var id: String { rawValue }

    var title: String {
        switch self {
        case .fullStudio: return "Full Studio"
        case .screenAndVoice: return "Screen + Voice"
        case .screenAndSystemAudio: return "Screen + System Audio"
        case .podcast: return "Podcast (audio only)"
        case .cameraOnly: return "Camera only"
        }
    }

    var profile: RecordingProfile {
        switch self {
        case .fullStudio:
            return .fullStudio
        case .screenAndVoice:
            return RecordingProfile(tracks: [.screen, .microphone])
        case .screenAndSystemAudio:
            return RecordingProfile(tracks: [.screen, .systemAudio])
        // Voice only, not voice + system audio: system audio would drag in the Screen
        // Recording permission that an audio-only recording otherwise never needs. A remote
        // guest is one visible toggle away, which makes it a choice rather than a surprise.
        case .podcast:
            return RecordingProfile(tracks: [.microphone])
        // With the mic, because a talking head with no voice is not a thing anyone records.
        case .cameraOnly:
            return RecordingProfile(tracks: [.camera, .microphone])
        }
    }

    /// The preset a profile corresponds to, or nil for Custom.
    static func matching(_ profile: RecordingProfile) -> RecordingPreset? {
        allCases.first { $0.profile == profile }
    }
}
