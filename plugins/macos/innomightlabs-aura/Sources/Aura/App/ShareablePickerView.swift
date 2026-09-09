import SwiftUI
import ScreenCaptureKit

struct ShareablePickerView: View {
    @ObservedObject var viewModel: ShareablePickerViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let loadError = viewModel.loadError {
                Text(loadError.localizedDescription)
                    .font(.caption)
                    .foregroundStyle(.red)
            }

            if viewModel.displays.isEmpty && viewModel.windows.isEmpty {
                Text("No displays or windows found.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                Picker("Record", selection: $viewModel.selectedTarget) {
                    Text("Select a source…").tag(CaptureTarget?.none)

                    if !viewModel.displays.isEmpty {
                        Section("Displays") {
                            ForEach(viewModel.displays, id: \.displayID) { display in
                                Text(CaptureTarget.display(display).displayName)
                                    .tag(CaptureTarget?.some(.display(display)))
                            }
                        }
                    }

                    if !viewModel.windows.isEmpty {
                        Section("Windows") {
                            ForEach(viewModel.windows, id: \.windowID) { window in
                                Text(CaptureTarget.window(window).displayName)
                                    .tag(CaptureTarget?.some(.window(window)))
                            }
                        }
                    }

                    if !viewModel.runningApps.isEmpty, let primaryDisplay = viewModel.displays.first {
                        Section("Apps") {
                            ForEach(viewModel.runningApps, id: \.processID) { app in
                                Text(CaptureTarget.app(app, on: primaryDisplay).displayName)
                                    .tag(CaptureTarget?.some(.app(app, on: primaryDisplay)))
                            }
                        }
                    }
                }
                .labelsHidden()
            }
        }
        .task {
            await viewModel.refresh()
        }
    }
}
