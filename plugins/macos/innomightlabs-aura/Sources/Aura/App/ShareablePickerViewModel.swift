import ScreenCaptureKit
import SwiftUI

@MainActor
final class ShareablePickerViewModel: ObservableObject {
    @Published private(set) var displays: [SCDisplay] = []
    @Published private(set) var windows: [SCWindow] = []
    @Published private(set) var runningApps: [SCRunningApplication] = []
    @Published var loadError: RecordingError?

    @Published var selectedTarget: CaptureTarget? {
        didSet { RecordingPreferences.lastCaptureTargetName = selectedTarget?.displayName }
    }

    func refresh() async {
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(
                false,
                onScreenWindowsOnly: true
            )
            displays = content.displays
            windows = content.windows.filter { $0.title?.isEmpty == false }
            runningApps = content.applications
            restoreSelectionIfNeeded()
        } catch {
            loadError = .screenRecordingPermissionDenied
        }
    }

    private func restoreSelectionIfNeeded() {
        guard selectedTarget == nil, let savedName = RecordingPreferences.lastCaptureTargetName else { return }
        selectedTarget = allTargets().first { $0.displayName == savedName }
    }

    private func allTargets() -> [CaptureTarget] {
        var targets = displays.map(CaptureTarget.display)
        targets += windows.map(CaptureTarget.window)
        if let primaryDisplay = displays.first {
            targets += runningApps.map { CaptureTarget.app($0, on: primaryDisplay) }
        }
        return targets
    }
}
