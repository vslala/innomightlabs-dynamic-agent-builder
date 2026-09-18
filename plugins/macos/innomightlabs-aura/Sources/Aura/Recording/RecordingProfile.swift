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
///
/// Declaration order is display order: `allCases` drives both preset pickers directly, widest
/// combination (every track) down to the narrowest (voice alone) — not alphabetical or by
/// track count, but by how a presenter would scan the list looking for "the one with screen
/// and system audio but no camera."
enum RecordingPreset: String, CaseIterable, Identifiable, Sendable {
    case fullStudio
    case screenVoiceCamera
    case screenVoiceSystemAudio
    case screenAndSystemAudio
    case screenAndVoice
    case voiceAndCamera
    case voiceOnly

    var id: String { rawValue }

    var title: String {
        switch self {
        case .fullStudio: return "Full Studio Recording"
        case .screenVoiceCamera: return "Screen + Voice + Camera"
        case .screenVoiceSystemAudio: return "Screen + Voice + System Audio"
        case .screenAndSystemAudio: return "Screen + System Audio"
        case .screenAndVoice: return "Screen + Voice"
        case .voiceAndCamera: return "Voice + Camera"
        case .voiceOnly: return "Voice Only"
        }
    }

    var profile: RecordingProfile {
        switch self {
        case .fullStudio:
            return .fullStudio
        case .screenVoiceCamera:
            return RecordingProfile(tracks: [.screen, .camera, .microphone])
        case .screenVoiceSystemAudio:
            return RecordingProfile(tracks: [.screen, .microphone, .systemAudio])
        // No microphone: this is the silent screen-plus-system-audio capture, distinct from
        // `screenVoiceSystemAudio` which adds a narrated voice track.
        case .screenAndSystemAudio:
            return RecordingProfile(tracks: [.screen, .systemAudio])
        case .screenAndVoice:
            return RecordingProfile(tracks: [.screen, .microphone])
        // With the mic, because a talking head with no voice is not a thing anyone records.
        case .voiceAndCamera:
            return RecordingProfile(tracks: [.camera, .microphone])
        // Voice only, not voice + system audio: system audio would drag in the Screen
        // Recording permission that an audio-only recording otherwise never needs. A remote
        // guest is one visible toggle away, which makes it a choice rather than a surprise.
        case .voiceOnly:
            return RecordingProfile(tracks: [.microphone])
        }
    }

    /// The preset a profile corresponds to, or nil for Custom.
    static func matching(_ profile: RecordingProfile) -> RecordingPreset? {
        allCases.first { $0.profile == profile }
    }
}
