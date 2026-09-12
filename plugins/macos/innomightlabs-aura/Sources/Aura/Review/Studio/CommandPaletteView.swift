import SwiftUI

/// Cmd+K. A search field over the command registry.
///
/// Keyboard handling is local rather than routed through `ReviewKeyCommand`: while the palette
/// is open its text field holds focus, so the global table correctly declines bare keystrokes,
/// and arrow/enter belong to the list rather than the timeline.
struct CommandPaletteView: View {
    @ObservedObject var viewModel: ReviewViewModel
    let onOpenSettings: () -> Void

    @State private var query = ""
    @State private var selection = 0
    @FocusState private var isFocused: Bool

    private var results: [StudioCommand] {
        CommandPalette.matching(query)
    }

    var body: some View {
        ZStack(alignment: .top) {
            // A scrim that closes on click, which is the expected way out of a palette.
            Color.black.opacity(0.45)
                .ignoresSafeArea()
                .onTapGesture { close() }

            panel
                .padding(.top, 120)
        }
        .onAppear { isFocused = true }
        .onKeyPress(.escape) {
            close()
            return .handled
        }
        .onKeyPress(.downArrow) {
            move(by: 1)
            return .handled
        }
        .onKeyPress(.upArrow) {
            move(by: -1)
            return .handled
        }
        .onKeyPress(.return) {
            runSelected()
            return .handled
        }
    }

    private var panel: some View {
        VStack(spacing: 0) {
            field
            Divider().overlay(AuraTheme.border)
            list
        }
        .frame(width: 560)
        .background {
            RoundedRectangle(cornerRadius: AuraTheme.Radius.lg)
                .fill(AuraTheme.surfaceElevated)
                .overlay {
                    RoundedRectangle(cornerRadius: AuraTheme.Radius.lg)
                        .stroke(AuraTheme.border, lineWidth: 1)
                }
                .shadow(color: .black.opacity(0.55), radius: 28, y: 12)
        }
        .clipShape(RoundedRectangle(cornerRadius: AuraTheme.Radius.lg))
    }

    private var field: some View {
        HStack(spacing: AuraTheme.Space.sm + 2) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 13))
                .foregroundStyle(AuraTheme.textSecondary)

            TextField("Search commands…", text: $query)
                .textFieldStyle(.plain)
                .font(.system(size: 14))
                .foregroundStyle(AuraTheme.textPrimary)
                .focused($isFocused)
                .onChange(of: query) { _, _ in selection = 0 }
        }
        .padding(.horizontal, AuraTheme.Space.md)
        .padding(.vertical, AuraTheme.Space.md - 2)
    }

    @ViewBuilder
    private var list: some View {
        if results.isEmpty {
            Text("No commands match “\(query)”")
                .font(.system(size: 12))
                .foregroundStyle(AuraTheme.textSecondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(AuraTheme.Space.md)
        } else {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(spacing: 0) {
                        ForEach(Array(results.enumerated()), id: \.element.id) { index, command in
                            row(command, isSelected: index == selection)
                                .id(command.id)
                                .onTapGesture { run(command) }
                        }
                    }
                    .padding(.vertical, AuraTheme.Space.xs)
                }
                .frame(maxHeight: 340)
                .onChange(of: selection) { _, new in
                    guard new < results.count else { return }
                    proxy.scrollTo(results[new].id, anchor: .center)
                }
            }
        }
    }

    private func row(_ command: StudioCommand, isSelected: Bool) -> some View {
        HStack(spacing: AuraTheme.Space.sm) {
            VStack(alignment: .leading, spacing: 1) {
                Text(command.title)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(AuraTheme.textPrimary)
                if let subtitle = command.subtitle {
                    Text(subtitle)
                        .font(.system(size: 11))
                        .foregroundStyle(AuraTheme.textSecondary)
                }
            }

            Spacer(minLength: AuraTheme.Space.md)

            if let shortcut = command.shortcut {
                Text(shortcut)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(AuraTheme.textTertiary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background {
                        RoundedRectangle(cornerRadius: 5).fill(AuraTheme.surface)
                    }
            }
        }
        .padding(.horizontal, AuraTheme.Space.md)
        .padding(.vertical, AuraTheme.Space.sm + 1)
        .background {
            if isSelected {
                RoundedRectangle(cornerRadius: AuraTheme.Radius.sm)
                    .fill(AuraTheme.accentFill(0.2))
                    .padding(.horizontal, AuraTheme.Space.sm)
            }
        }
        .contentShape(Rectangle())
    }

    // MARK: - Behaviour

    private func move(by delta: Int) {
        guard !results.isEmpty else { return }
        selection = (selection + delta + results.count) % results.count
    }

    private func runSelected() {
        guard selection < results.count else { return }
        run(results[selection])
    }

    private func run(_ command: StudioCommand) {
        close()
        perform(command.action)
    }

    private func close() {
        viewModel.isCommandPaletteOpen = false
        query = ""
        selection = 0
    }

    private func perform(_ action: StudioCommand.Action) {
        switch action {
        case .studio(let studio):
            viewModel.perform(studio)
        case .splitAtPlayhead:
            viewModel.splitAtPlayhead()
        case .deleteSelection:
            viewModel.cutSelection()
        case .addMarker:
            viewModel.addMarkerAtPlayhead()
        case .layout(let mode):
            viewModel.setLayoutMode(mode)
        case .export:
            NotificationCenter.default.post(name: .auraExportRequested, object: nil)
        case .openTranscript:
            viewModel.rightPanel = .transcript
            viewModel.activeSection = .transcript
        case .openAI:
            viewModel.rightPanel = .ai
        case .zoomIn:
            viewModel.zoomIn()
        case .zoomOut:
            viewModel.zoomOut()
        case .zoomToFit:
            viewModel.zoomToFit()
        case .toggleCaptions:
            viewModel.showsCaptions.toggle()
        case .armBlade:
            viewModel.isBladeArmed = true
        }
    }
}
