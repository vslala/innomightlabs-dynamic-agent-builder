import SwiftUI

/// The left navigation. Deliberately tiny — the recording being edited is the main object, not
/// a file browser, so this is orientation rather than a place to spend screen width.
struct StudioSidebarView: View {
    @ObservedObject var viewModel: ReviewViewModel
    let onSelect: (StudioSection) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: AuraTheme.Space.xs) {
            ForEach(StudioSection.primary) { section in
                item(section)
            }

            Spacer(minLength: 0)

            item(.settings)
        }
        .padding(.horizontal, AuraTheme.Space.sm)
        .padding(.vertical, AuraTheme.Space.md)
        .frame(width: 188, alignment: .leading)
        .background(AuraTheme.surface)
    }

    private func item(_ section: StudioSection) -> some View {
        let isActive = viewModel.activeSection == section

        return Button {
            onSelect(section)
        } label: {
            HStack(spacing: AuraTheme.Space.sm + 2) {
                Image(systemName: section.symbol)
                    .font(.system(size: 13, weight: .medium))
                    .frame(width: 18)
                Text(section.title)
                    .font(.system(size: 13, weight: isActive ? .semibold : .regular))
                Spacer(minLength: 0)
            }
            .foregroundStyle(foreground(section, isActive: isActive))
            .padding(.horizontal, AuraTheme.Space.sm + 2)
            .padding(.vertical, AuraTheme.Space.sm + 1)
            .background {
                // Elevation for the active row rather than a border, per the design rules.
                RoundedRectangle(cornerRadius: AuraTheme.Radius.md)
                    .fill(isActive ? AuraTheme.surfaceElevated : .clear)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!section.isAvailable)
        .help(section.unavailableReason ?? section.title)
    }

    private func foreground(_ section: StudioSection, isActive: Bool) -> Color {
        guard section.isAvailable else { return AuraTheme.textTertiary }
        return isActive ? AuraTheme.textPrimary : AuraTheme.textSecondary
    }
}
