import SwiftUI

/// The top strip: identity on the left, the session being edited in the middle, history and the
/// one primary action on the right.
///
/// Runs under the window's titlebar, so it reserves leading space for the traffic lights.
struct StudioHeaderView: View {
    @ObservedObject var viewModel: ReviewViewModel

    @State private var isRenaming = false
    @State private var draftName = ""

    var body: some View {
        HStack(spacing: AuraTheme.Space.md) {
            identity

            Spacer(minLength: AuraTheme.Space.md)

            sessionName
            recordedBadge

            Spacer(minLength: AuraTheme.Space.md)

            history
            ExportButton(viewModel: viewModel)
        }
        .padding(.leading, AuraTheme.trafficLightInset)
        .padding(.trailing, AuraTheme.Space.md)
        .frame(height: 52)
        .background(AuraTheme.background)
    }

    private var identity: some View {
        HStack(spacing: AuraTheme.Space.sm) {
            Image("AuraMark")
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 20, height: 20)
            Text("Aura Studio")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(AuraTheme.textPrimary)
        }
        .fixedSize()
    }

    private var sessionName: some View {
        Menu {
            Button("Rename…") {
                draftName = viewModel.sessionName
                isRenaming = true
            }
            Button("Reveal in Finder") { viewModel.revealInFinder() }
        } label: {
            HStack(spacing: AuraTheme.Space.xs + 2) {
                Text(viewModel.sessionName)
                    .font(.system(size: 13, weight: .medium))
                    .lineLimit(1)
                Image(systemName: "chevron.down")
                    .font(.system(size: 9, weight: .semibold))
            }
            .foregroundStyle(AuraTheme.textPrimary)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .popover(isPresented: $isRenaming, arrowEdge: .bottom) { renameField }
    }

    private var renameField: some View {
        VStack(alignment: .leading, spacing: AuraTheme.Space.sm) {
            Text("Session name")
                .font(.caption)
                .foregroundStyle(AuraTheme.textSecondary)
            TextField("Name", text: $draftName)
                .textFieldStyle(.roundedBorder)
                .frame(width: 240)
                .onSubmit(commitRename)
            HStack {
                Spacer()
                Button("Cancel") { isRenaming = false }
                Button("Save", action: commitRename)
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(AuraTheme.Space.md)
    }

    private func commitRename() {
        viewModel.rename(to: draftName)
        isRenaming = false
    }

    /// A statement of provenance, not a control — so it is quiet and not interactive.
    private var recordedBadge: some View {
        HStack(spacing: AuraTheme.Space.xs + 2) {
            Circle()
                .fill(AuraTheme.accent)
                .frame(width: 5, height: 5)
            Text("Recorded in Aura")
                .font(.system(size: 11))
                .foregroundStyle(AuraTheme.textSecondary)
        }
        .padding(.horizontal, AuraTheme.Space.sm + 2)
        .padding(.vertical, 5)
        .background {
            Capsule().fill(AuraTheme.surfaceElevated)
        }
        .fixedSize()
    }

    @ViewBuilder
    private var history: some View {
        if let store = viewModel.store {
            HStack(spacing: AuraTheme.Space.xs) {
                iconButton("arrow.uturn.backward", help: "Undo (⌘Z)", enabled: store.canUndo) {
                    store.undo()
                }
                iconButton("arrow.uturn.forward", help: "Redo (⇧⌘Z)", enabled: store.canRedo) {
                    store.redo()
                }
            }
        }
    }

    private func iconButton(
        _ symbol: String,
        help: String,
        enabled: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 12, weight: .medium))
                .frame(width: 28, height: 28)
                .foregroundStyle(enabled ? AuraTheme.textSecondary : AuraTheme.textTertiary)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .help(help)
    }
}
