import SwiftUI

/// The right column: the AI copilot, or the transcript.
///
/// Tabs rather than the previous stacked split, because both are primary editing surfaces that
/// want the full height — sharing it gave each half a cramped scroll view.
struct RightPanelView: View {
    @ObservedObject var viewModel: ReviewViewModel

    var body: some View {
        VStack(spacing: 0) {
            tabs

            switch viewModel.rightPanel {
            case .ai:
                AgentEditPanelView(viewModel: viewModel)
            case .transcript:
                TranscriptPanelView(viewModel: viewModel)
            }
        }
        .background(AuraTheme.surface)
    }

    private var tabs: some View {
        HStack(spacing: 0) {
            ForEach(ReviewViewModel.RightPanel.allCases, id: \.self) { tab in
                tabButton(tab)
            }
        }
        .padding(.horizontal, AuraTheme.Space.sm)
        .padding(.top, AuraTheme.Space.sm)
    }

    private func tabButton(_ tab: ReviewViewModel.RightPanel) -> some View {
        let isActive = viewModel.rightPanel == tab

        return Button {
            viewModel.rightPanel = tab
        } label: {
            VStack(spacing: AuraTheme.Space.sm) {
                HStack(spacing: AuraTheme.Space.xs + 2) {
                    Image(systemName: tab.symbol)
                        .font(.system(size: 11, weight: .medium))
                    Text(tab.title)
                        .font(.system(size: 12, weight: isActive ? .semibold : .regular))
                }
                .foregroundStyle(isActive ? AuraTheme.textPrimary : AuraTheme.textSecondary)

                // An underline marks the active tab rather than a filled pill, which keeps the
                // accent for things that are actions.
                Rectangle()
                    .fill(isActive ? AuraTheme.accent : Color.clear)
                    .frame(height: 2)
            }
            .frame(maxWidth: .infinity)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
