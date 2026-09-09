import SwiftUI

struct MenuBarContentView: View {
    @ObservedObject var controller: RecordingController
    @StateObject private var pickerViewModel = ShareablePickerViewModel()
    @StateObject private var cameraPickerViewModel = CameraPickerViewModel()

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
                Group {
                    ShareablePickerView(viewModel: pickerViewModel)

                    if !cameraPickerViewModel.cameras.isEmpty {
                        Picker("Camera", selection: $cameraPickerViewModel.selectedDeviceID) {
                            Text("Default").tag(String?.none)
                            ForEach(cameraPickerViewModel.cameras, id: \.uniqueID) { camera in
                                Text(camera.localizedName).tag(String?.some(camera.uniqueID))
                            }
                        }
                        .labelsHidden()
                    }

                    Button("Start Recording") {
                        guard let target = pickerViewModel.selectedTarget else { return }
                        let cameraDeviceID = cameraPickerViewModel.selectedDeviceID
                        Task { await controller.start(target: target, cameraDeviceID: cameraDeviceID) }
                    }
                    .disabled(pickerViewModel.selectedTarget == nil)
                }
                .task { cameraPickerViewModel.refresh() }

            case .starting:
                HStack {
                    ProgressView().controlSize(.small)
                    Text("Starting…")
                }

            case .recording, .paused:
                Text(controller.state == .recording ? "Recording" : "Paused")
                    .font(.headline)
                if let name = controller.currentTargetName {
                    Text(name)
                        .font(.caption)
                        .foregroundStyle(.secondary)
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

            case .stopping:
                HStack {
                    ProgressView().controlSize(.small)
                    Text("Saving…")
                }
            }

            Divider()

            Button("Quit") {
                NSApplication.shared.terminate(nil)
            }
        }
        .padding(12)
        .frame(width: 260)
    }
}
