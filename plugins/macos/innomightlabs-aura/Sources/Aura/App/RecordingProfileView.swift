import SwiftUI

/// The menu bar's source picker — one clickable tile per `TrackKind` — plus whichever device
/// pickers the selected sources actually need.
///
/// Tiles rather than `Toggle`s: they rely on `AuraApp` forcing `.menuBarExtraStyle(.window)`,
/// without which every custom control degrades to a bare `NSMenu` checkmark.
struct RecordingProfileView: View {
    @ObservedObject var setup: RecordingSetupViewModel
    @ObservedObject var screenPicker: ShareablePickerViewModel
    @ObservedObject var cameraPicker: CameraPickerViewModel
    @ObservedObject var microphonePicker: MicrophonePickerViewModel
    @StateObject private var levelMonitor = InputLevelMonitor()

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            sourceTiles

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

    private var sourceTiles: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 6) {
            ForEach(TrackKind.allCases, id: \.self) { kind in
                SourceTile(kind: kind, isOn: setup.profile.tracks.contains(kind)) {
                    setup.toggle(kind)
                }
            }
        }
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

/// One source the user can switch on or off with a click.
private struct SourceTile: View {
    let kind: TrackKind
    let isOn: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: kind.symbol)
                    .frame(width: 16)
                Text(kind.title)
                    .lineLimit(1)
                Spacer(minLength: 0)
                Image(systemName: isOn ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(isOn ? Color.accentColor : Color.secondary)
            }
            .font(.system(size: 12, weight: .medium))
            .padding(.horizontal, 8)
            .padding(.vertical, 7)
            .background {
                RoundedRectangle(cornerRadius: 6)
                    .fill(isOn ? Color.accentColor.opacity(0.18) : Color.secondary.opacity(0.08))
            }
            .overlay {
                RoundedRectangle(cornerRadius: 6)
                    .strokeBorder(isOn ? Color.accentColor.opacity(0.6) : Color.clear)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isOn ? .isSelected : [])
        .help(isOn ? "Stop recording \(kind.title)" : "Record \(kind.title)")
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
