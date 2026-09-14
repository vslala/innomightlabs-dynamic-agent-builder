import AVFoundation
import SwiftUI

/// The studio shell.
///
/// Layout only — header, navigation, preview, right panel, timeline. It holds no editing logic,
/// which is what keeps the arrangement changeable without touching anything that can break a
/// timeline.
///
/// The timeline takes a fraction of the height rather than a fixed number of points, so the
/// preview keeps the majority of the area at any window size.
struct ReviewWindowView: View {
    @ObservedObject var viewModel: ReviewViewModel

    @State private var showingSettings = false

    var body: some View {
        ZStack {
            AuraTheme.background.ignoresSafeArea()

            switch viewModel.state {
            case .loading:
                loading
            case .failed(let message):
                failure(message)
            case .ready:
                studio
            }
        }
        .frame(minWidth: 1100, minHeight: 720)
        .environment(\.colorScheme, .dark)
        .task { await viewModel.load() }
        .sheet(isPresented: $showingSettings) { AgentSettingsView() }
    }

    // MARK: - States

    private var loading: some View {
        VStack(spacing: AuraTheme.Space.md) {
            ProgressView()
            Text("Opening \(viewModel.sessionName)…")
                .font(.system(size: 12))
                .foregroundStyle(AuraTheme.textSecondary)
        }
    }

    private func failure(_ message: String) -> some View {
        VStack(spacing: AuraTheme.Space.md) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 26))
                .foregroundStyle(AuraTheme.textSecondary)
            Text(message)
                .font(.system(size: 13))
                .foregroundStyle(AuraTheme.textPrimary)
                .multilineTextAlignment(.center)
        }
        .padding(AuraTheme.Space.xl)
    }

    // MARK: - Studio

    private var studio: some View {
        GeometryReader { geometry in
            let timelineHeight = AuraTheme.Timeline.height(forWindowHeight: geometry.size.height)

            VStack(spacing: 0) {
                StudioHeaderView(viewModel: viewModel)

                HStack(spacing: 0) {
                    StudioSidebarView(viewModel: viewModel, onSelect: select)

                    VStack(spacing: 0) {
                        Group {
                            if viewModel.hasVideo {
                                PreviewStageView(viewModel: viewModel)
                            } else {
                                AudioStageView(viewModel: viewModel)
                            }
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .clipShape(RoundedRectangle(cornerRadius: AuraTheme.Radius.lg))

                        PreviewScrubBar(viewModel: viewModel)
                            .padding(.horizontal, AuraTheme.Space.xs)

                        PreviewControlsView(viewModel: viewModel, onToggleFullScreen: toggleFullScreen)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(AuraTheme.Space.md)

                    RightPanelView(viewModel: viewModel)
                        .frame(width: 380)
                }
                .frame(maxHeight: .infinity)

                TimelineView(viewModel: viewModel)
                    .frame(height: timelineHeight)
            }
        }
        .overlay(alignment: .top) { banners }
        .overlay {
            if viewModel.isCommandPaletteOpen {
                CommandPaletteView(viewModel: viewModel, onOpenSettings: { showingSettings = true })
            }
        }
    }

    private func select(_ section: StudioSection) {
        viewModel.activeSection = section
        switch section {
        case .transcript:
            viewModel.rightPanel = .transcript
        case .export:
            viewModel.rightPanel = .ai
            NotificationCenter.default.post(name: .auraExportRequested, object: nil)
        case .settings:
            showingSettings = true
        case .library, .sessions:
            break
        }
    }

    private func toggleFullScreen() {
        NSApp.keyWindow?.toggleFullScreen(nil)
    }

    // MARK: - Banners

    @ViewBuilder
    private var banners: some View {
        VStack(spacing: AuraTheme.Space.sm) {
            if let message = viewModel.lastError {
                banner(message, tint: ReviewPalette.cut) { viewModel.lastError = nil }
            }
            // Distinct from the error banner on purpose: a notice reports something expected,
            // and colouring it red would make a benign event look like a failure.
            if let notice = viewModel.lastNotice {
                banner(notice, tint: AuraTheme.accent) { viewModel.lastNotice = nil }
            }
        }
        .padding(.top, 60)
        .padding(.horizontal, AuraTheme.Space.lg)
    }

    private func banner(
        _ message: String,
        tint: Color,
        dismiss: @escaping () -> Void
    ) -> some View {
        HStack(spacing: AuraTheme.Space.sm) {
            Circle().fill(tint).frame(width: 6, height: 6)
            Text(message)
                .font(.system(size: 12))
                .foregroundStyle(AuraTheme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: AuraTheme.Space.md)
            Button("Dismiss", action: dismiss)
                .buttonStyle(.plain)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(AuraTheme.textSecondary)
        }
        .padding(.horizontal, AuraTheme.Space.md)
        .padding(.vertical, AuraTheme.Space.sm + 2)
        .background {
            RoundedRectangle(cornerRadius: AuraTheme.Radius.md)
                .fill(AuraTheme.surfaceElevated)
                .overlay {
                    RoundedRectangle(cornerRadius: AuraTheme.Radius.md)
                        .stroke(tint.opacity(0.35), lineWidth: 1)
                }
                .shadow(color: .black.opacity(0.4), radius: 12, y: 4)
        }
        .frame(maxWidth: 560)
    }
}

extension Notification.Name {
    /// Lets the sidebar's Export item trigger the same save panel the header button opens,
    /// without the sidebar having to own the export flow.
    static let auraExportRequested = Notification.Name("aura.exportRequested")
}
