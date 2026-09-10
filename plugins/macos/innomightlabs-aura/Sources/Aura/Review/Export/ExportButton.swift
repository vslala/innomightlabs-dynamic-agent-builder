import AppKit
import SwiftUI

struct ExportButton: View {
    @ObservedObject var viewModel: ReviewViewModel

    var body: some View {
        switch viewModel.exportState {
        case .idle:
            Button {
                viewModel.export()
            } label: {
                Label("Export", systemImage: "square.and.arrow.up")
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

        case .failed(let reason):
            Button {
                viewModel.export()
            } label: {
                Label("Export Failed", systemImage: "exclamationmark.triangle")
            }
            .help(reason)
        }
    }
}
