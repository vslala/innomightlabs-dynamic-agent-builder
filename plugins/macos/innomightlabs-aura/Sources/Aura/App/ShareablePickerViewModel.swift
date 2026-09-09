import ScreenCaptureKit
import SwiftUI

@MainActor
final class ShareablePickerViewModel: ObservableObject {
    @Published private(set) var displays: [SCDisplay] = []
    @Published private(set) var windows: [SCWindow] = []
    @Published private(set) var runningApps: [SCRunningApplication] = []
    @Published var selectedTarget: CaptureTarget?
    @Published var loadError: RecordingError?

    func refresh() async {
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(
                false,
                onScreenWindowsOnly: true
            )
            displays = content.displays
            windows = content.windows.filter { $0.title?.isEmpty == false }
            runningApps = content.applications
        } catch {
            loadError = .screenRecordingPermissionDenied
        }
    }
}
