import SwiftUI

/// The menu bar's mode picker, plus whichever device pickers the selected preset actually
/// needs.
///
/// Presets only — no per-source toggles. A `MenuBarExtra` with no `.menuBarExtraStyle(.window)`
/// silently degrades every custom control to a native `NSMenu` item (a `Picker` becomes a
/// nested submenu, a `Toggle` becomes a bare checkmark, a hand-drawn view like the level meter
/// doesn't render at all), which made the four-toggle "Sources" disclosure read as a maze of
/// checkmarks and submenus rather than a settings panel. `AuraApp` now forces `.window` style,
/// but the simpler surface — one mode picker, and only the device controls that mode needs — is
/// worth keeping regardless: "what am I recording" is one decision, not four independent ones
/// most people never touch.
struct RecordingProfileView: View {
    @ObservedObject var setup: RecordingSetupViewModel
    @ObservedObject var screenPicker: ShareablePickerViewModel
    @ObservedObject var cameraPicker: CameraPickerViewModel
    @ObservedObject var microphonePicker: MicrophonePickerViewModel
    @StateObject private var levelMonitor = InputLevelMonitor()

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            modeMenu

            if setup.profile.tracks.contains(.screen) {
                ShareablePickerView(viewModel: screenPicker)
            }

            if setup.profile.tracks.contains(.camera) {
                Picker("Camera", selection: $cameraPicker.selectedDeviceID) {
                    Text("Default").tag(String?.none)
                    ForEach(cameraPicker.cameras, id: \.uniqueID) { camera in
                        Text(camera.localizedName).tag(String?.some(camera.uniqueID))
                    }
                }
                .labelsHidden()
            }

            if setup.profile.tracks.contains(.microphone) {
                microphoneControls
            }

            // Discovering this through a permission prompt on a podcast reads as a bug, so it
            // is said up front instead.
            if setup.profile.tracks.contains(.systemAudio), !setup.profile.tracks.contains(.screen) {
                Text("Requires Screen Recording permission — system audio is captured through it.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var modeMenu: some View {
        Picker("Mode", selection: modeBinding) {
            ForEach(RecordingPreset.allCases) { preset in
                Text(preset.title).tag(preset)
            }
        }
        .labelsHidden()
    }

    private var modeBinding: Binding<RecordingPreset> {
        Binding(
            get: { setup.preset ?? .fullStudio },
            set: { setup.apply($0) }
        )
    }

    private var microphoneControls: some View {
        VStack(alignment: .leading, spacing: 4) {
            Picker("Microphone", selection: $microphonePicker.selectedDeviceID) {
                Text("Default").tag(String?.none)
                ForEach(microphonePicker.microphones, id: \.uniqueID) { microphone in
                    Text(microphone.localizedName).tag(String?.some(microphone.uniqueID))
                }
            }
            .labelsHidden()

            LevelMeterView(monitor: levelMonitor)
        }
        .onAppear { levelMonitor.start(deviceID: microphonePicker.selectedDeviceID) }
        .onDisappear { levelMonitor.stop() }
        .onChange(of: microphonePicker.selectedDeviceID) { _, newDeviceID in
            levelMonitor.start(deviceID: newDeviceID)
        }
    }
}

/// A thin bar plus a numeric dBFS readout. Muting is a separate concern (`mute()`/`unmute()`
/// on `RecordingController`, only meaningful once recording) — this view only ever reports
/// what the microphone is picking up.
private struct LevelMeterView: View {
    @ObservedObject var monitor: InputLevelMonitor

    var body: some View {
        HStack(spacing: 6) {
            GeometryReader { geometry in
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.secondary.opacity(0.2))
                    .overlay(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(monitor.level > 0.85 ? Color.red : Color.green)
                            .frame(width: geometry.size.width * monitor.level)
                    }
            }
            .frame(height: 6)

            Text(readout)
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(.secondary)
                .frame(width: 40, alignment: .trailing)
        }
    }

    private var readout: String {
        monitor.dbFS <= InputLevelMeter.floor ? "—" : "\(Int(monitor.dbFS)) dB"
    }
}
