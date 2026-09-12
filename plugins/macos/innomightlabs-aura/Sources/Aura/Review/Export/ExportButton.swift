import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct ExportButton: View {
    @ObservedObject var viewModel: ReviewViewModel

    var body: some View {
        content
            // The sidebar's Export item and the command palette both route here, so the save
            // panel lives in one place rather than being duplicated per entry point.
            .onReceive(.auraExportRequested) {
                guard case .idle = viewModel.exportState else { return }
                chooseDestination()
            }
    }

    @ViewBuilder
    private var content: some View {
        switch viewModel.exportState {
        case .idle:
            primary(title: "Export", symbol: "square.and.arrow.up") { chooseDestination() }
                .disabled(viewModel.timeline == nil)

        case .running(let fraction):
            HStack(spacing: AuraTheme.Space.sm) {
                ProgressView(value: fraction)
                    .frame(width: 76)
                Button("Cancel") { viewModel.cancelExport() }
                    .buttonStyle(.plain)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(AuraTheme.textSecondary)
            }

        case .finished(let url):
            primary(title: "Show in Finder", symbol: "checkmark.circle") {
                NSWorkspace.shared.activateFileViewerSelecting([url])
            }
            .help(url.path)

        case .failed(let reason):
            primary(title: "Export Failed", symbol: "exclamationmark.triangle", tint: ReviewPalette.cut) {
                chooseDestination()
            }
            .help(reason)
        }
    }

    /// The window's one filled button. Everything else is quiet, so this reads as *the* action.
    private func primary(
        title: String,
        symbol: String,
        tint: Color = AuraTheme.accent,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: AuraTheme.Space.sm - 2) {
                Image(systemName: symbol)
                    .font(.system(size: 11, weight: .semibold))
                Text(title)
                    .font(.system(size: 12, weight: .semibold))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, AuraTheme.Space.md - 2)
            .padding(.vertical, AuraTheme.Space.sm)
            .background {
                RoundedRectangle(cornerRadius: AuraTheme.Radius.sm)
                    .fill(tint)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
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
