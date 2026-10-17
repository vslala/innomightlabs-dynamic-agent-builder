import SwiftUI

/// What the menu bar's recording popover is about to record.
///
/// `profile` is the source of truth, built by toggling sources.
@MainActor
final class RecordingSetupViewModel: ObservableObject {
    @Published var profile: RecordingProfile {
        didSet { RecordingPreferences.lastProfile = profile }
    }

    func toggle(_ kind: TrackKind) {
        if profile.tracks.contains(kind) {
            profile.tracks.remove(kind)
        } else {
            profile.tracks.insert(kind)
        }
    }

    init() {
        // An empty profile persisted from an earlier session is not recordable, so it starts
        // from the full studio instead of a popover with nothing selected.
        if let restored = RecordingPreferences.lastProfile, restored.isRecordable {
            profile = restored
        } else {
            profile = .fullStudio
        }
    }
}
