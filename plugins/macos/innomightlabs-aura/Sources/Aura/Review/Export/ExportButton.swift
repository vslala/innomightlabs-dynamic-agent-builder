import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct ExportButton: View {
    @ObservedObject var viewModel: ReviewViewModel

    var body: some View {
        switch viewModel.exportState {
        case .idle:
            Button {
                chooseDestination()
            } label: {
                Label("Export…", systemImage: "square.and.arrow.up")
            }
            .disabled(viewModel.timeline == nil)

        case .running(let fraction):
            HStack(spacing: 6) {
                ProgressView(value: fraction)
                    .frame(width: 70)
                Button("Cancel") { viewModel.cancelExport() }
                    .font(.caption)
            }

        case .finished(let url):
            Button {
                NSWorkspace.shared.activateFileViewerSelecting([url])
            } label: {
                Label("Show in Finder", systemImage: "checkmark.circle")
            }
            .help(url.path)

        case .failed(let reason):
            Button {
                chooseDestination()
            } label: {
                Label("Export Failed", systemImage: "exclamationmark.triangle")
            }
            .help(reason)
        }
    }

    /// Asks where to write before doing any work. The panel also owns the overwrite
    /// confirmation and the sandbox permission for wherever the user picks, which is why the
    /// destination comes from here rather than being decided for them.
    private func chooseDestination() {
        let suggested = viewModel.suggestedExportURL
        let panel = NSSavePanel()
        panel.title = "Export Recording"
        panel.nameFieldStringValue = suggested.lastPathComponent
        panel.directoryURL = suggested.deletingLastPathComponent()
        panel.allowedContentTypes = [.mpeg4Movie]
        panel.canCreateDirectories = true
        panel.isExtensionHidden = false

        guard panel.runModal() == .OK, let url = panel.url else { return }
        viewModel.export(to: url)
    }
}
