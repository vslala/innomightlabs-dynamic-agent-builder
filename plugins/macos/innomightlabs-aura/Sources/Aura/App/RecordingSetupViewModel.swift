import SwiftUI

/// What the menu bar's recording popover is about to record.
///
/// `profile` is the source of truth; a preset is a shortcut that writes it. There is
/// deliberately no per-source override any more — see `RecordingProfileView` for why — so
/// `profile` always matches exactly one `RecordingPreset`.
@MainActor
final class RecordingSetupViewModel: ObservableObject {
    @Published var profile: RecordingProfile {
        didSet { RecordingPreferences.lastProfile = profile }
    }

    var preset: RecordingPreset? { RecordingPreset.matching(profile) }

    func apply(_ preset: RecordingPreset) {
        profile = preset.profile
    }

    init() {
        let restored = RecordingPreferences.lastProfile ?? .fullStudio
        // A value persisted by a now-removed per-source toggle UI could be a combination no
        // preset matches. Normalized here rather than left to display as some arbitrary
        // preset while silently recording something else.
        profile = RecordingPreset.matching(restored) != nil ? restored : .fullStudio
    }
}
