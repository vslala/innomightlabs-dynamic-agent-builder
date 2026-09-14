import SwiftUI

struct MenuBarContentView: View {
    @ObservedObject var controller: RecordingController
    @StateObject private var setup = RecordingSetupViewModel()
    @StateObject private var screenPicker = ShareablePickerViewModel()
    @StateObject private var cameraPicker = CameraPickerViewModel()
    @StateObject private var microphonePicker = MicrophonePickerViewModel()
    let reviewWindows: ReviewWindowPresenter

    /// Enumerated once when the menu opens rather than on every body pass — reading it
    /// twice per pass meant a directory scan per redraw on the main thread.
    @State private var recentSessions: [SessionFolder] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let lastError = controller.lastError {
                HStack {
                    Text(lastError.localizedDescription)
                        .font(.caption)
                        .foregroundStyle(.red)
                    Spacer()
                    Button("Dismiss") { controller.lastError = nil }
                        .font(.caption)
                }
            }

            switch controller.state {
            case .idle:
                idleContent

            case .starting:
                HStack {
                    ProgressView().controlSize(.small)
                    Text("Starting…")
                }

            case .recording, .paused:
                recordingContent

            case .stopping:
                HStack {
                    ProgressView().controlSize(.small)
                    Text("Saving…")
                }
            }

            Divider()

            if !recentSessions.isEmpty {
                Menu("Open Recording") {
                    ForEach(recentSessions, id: \.id) { session in
                        Button(session.id) { reviewWindows.open(session) }
                    }
                }
            }

            Button("Quit") {
                NSApplication.shared.terminate(nil)
            }
        }
        .padding(12)
        .frame(width: 300)
        .task {
            recentSessions = Array(SessionFolder.existingSessions().prefix(10))
        }
    }

    // MARK: - Idle

    private var idleContent: some View {
        VStack(alignment: .leading, spacing: 8) {
            RecordingProfileView(
                setup: setup,
                screenPicker: screenPicker,
                cameraPicker: cameraPicker,
                microphonePicker: microphonePicker
            )

            if let reason = validationReason {
                Text(reason)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Button("Start Recording") {
                Task { await controller.start(currentRequest) }
            }
            .disabled(!currentRequest.isValid)
        }
        .task {
            // The screen picker is refreshed here regardless of whether the Screen row is
            // visible: a System Audio-only profile still needs `screenPicker.displays` for the
            // fallback filter target in `currentRequest`.
            await screenPicker.refresh()
            cameraPicker.refresh()
            microphonePicker.refresh()
        }
    }

    /// System audio still needs an `SCContentFilter`, so when Screen is off but System Audio
    /// is on, the primary display stands in for it — the stream attaches no `.screen` output,
    /// so nothing about *what* is recorded changes.
    private var currentRequest: RecordingRequest {
        RecordingRequest(
            profile: setup.profile,
            screenTarget: screenPicker.selectedTarget ?? screenPicker.displays.first.map(CaptureTarget.display),
            cameraDeviceID: cameraPicker.selectedDeviceID,
            microphoneDeviceID: microphonePicker.selectedDeviceID
        )
    }

    private var validationReason: String? {
        guard !currentRequest.isValid else { return nil }
        guard setup.profile.isRecordable else { return "Pick at least one thing to record." }
        return "Choose a display or window."
    }

    // MARK: - Recording

    private var recordingContent: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(controller.state == .recording ? "Recording" : "Paused")
                .font(.headline)
            if let profile = controller.currentProfile {
                Text(profile.enabledKinds.map(\.title).joined(separator: ", "))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            // Only while actively recording: a source added mid-pause would need a
            // `PauseClock` seeded already-paused, which switching while paused is deferred
            // rather than getting subtly wrong. See the Phase 7 design doc.
            if controller.state == .recording {
                Picker("Preset", selection: presetBinding) {
                    ForEach(RecordingPreset.allCases) { preset in
                        Text(preset.title).tag(Optional(preset))
                    }
                }
                .labelsHidden()
                .pickerStyle(.menu)
                .font(.caption)
            }
            HStack {
                if controller.state == .recording {
                    Button("Pause") { controller.pause() }
                } else {
                    Button("Resume") { controller.resume() }
                }
                Button("Stop") {
                    Task { await controller.stop() }
                }
            }
        }
    }

    /// `nil` when the live profile matches no preset ("Custom"). Picking a preset from there
    /// moves the recording onto it; there is no UI for moving back to an arbitrary Custom
    /// profile mid-take, matching the picker showing presets only in `RecordingProfileView`.
    private var presetBinding: Binding<RecordingPreset?> {
        Binding(
            get: { controller.currentProfile.flatMap(RecordingPreset.matching) },
            set: { preset in
                guard let preset else { return }
                Task { await controller.switchProfile(to: preset.profile) }
            }
        )
    }
}
