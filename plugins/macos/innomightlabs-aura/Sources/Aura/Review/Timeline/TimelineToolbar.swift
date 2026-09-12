import SwiftUI

/// The strip above the lanes: the playhead readout, whatever the current selection affords, and
/// zoom. Controls appear only when they apply — there is no selection toolbar until there is a
/// selection.
struct TimelineToolbar: View {
    @ObservedObject var viewModel: ReviewViewModel

    var body: some View {
        HStack(spacing: AuraTheme.Space.sm) {
            timecodeChip

            if viewModel.isBladeArmed {
                badge("Blade — click to split", symbol: "scissors", tint: ReviewPalette.cut)
            }

            if let selection = viewModel.selection {
                selectionControls(selection)
            } else if let region = viewModel.selectedCutRegion {
                cutControls(region)
            }

            Spacer(minLength: AuraTheme.Space.sm)

            if !viewModel.isPlayheadVisible, viewModel.visibleDuration != nil {
                Button("Playhead") { viewModel.scrollToPlayhead() }
                    .buttonStyle(.plain)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(AuraTheme.accent)
                    .help("Centre the view on the playhead")
            }

            followToggle

            markerMenu
            zoomControls
        }
        .padding(.horizontal, AuraTheme.Space.md)
        .frame(height: 44)
    }

    private var timecodeChip: some View {
        Text(TimeFormatting.timecode(Timeline.seconds(viewModel.playhead)))
            .font(.system(size: 11, weight: .medium, design: .monospaced))
            .foregroundStyle(AuraTheme.textPrimary)
            .padding(.horizontal, AuraTheme.Space.sm)
            .padding(.vertical, 4)
            .background {
                RoundedRectangle(cornerRadius: 6).fill(AuraTheme.accentFill(0.22))
            }
    }

    private func badge(_ text: String, symbol: String, tint: Color) -> some View {
        HStack(spacing: AuraTheme.Space.xs + 1) {
            Image(systemName: symbol).font(.system(size: 9, weight: .semibold))
            Text(text).font(.system(size: 10, weight: .medium))
        }
        .foregroundStyle(tint)
        .padding(.horizontal, AuraTheme.Space.sm)
        .padding(.vertical, 3)
        .background { Capsule().fill(tint.opacity(0.14)) }
    }

    /// A selection reports both its span and how much of it survives: after cuts the two
    /// differ, and the difference is easy to misjudge.
    private func selectionControls(_ selection: StampSpan<Source>) -> some View {
        let kept = viewModel.projection.keptDuration(in: selection)

        return HStack(spacing: AuraTheme.Space.sm) {
            VStack(alignment: .leading, spacing: 0) {
                Text(String(format: "%.2fs selected", selection.duration))
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(AuraTheme.textPrimary)
                if abs(kept - selection.duration) > 0.005 {
                    Text(String(format: "%.2fs kept", kept))
                        .font(.system(size: 9))
                        .foregroundStyle(AuraTheme.textTertiary)
                }
            }
            .fixedSize()

            action("Delete", symbol: "scissors", tint: ReviewPalette.cut, enabled: kept > 0) {
                viewModel.cutSelection()
            }
            action("Split", symbol: "square.split.2x1", tint: AuraTheme.textSecondary) {
                viewModel.splitAtSelectionStart()
            }
            action("Clear", symbol: "xmark", tint: AuraTheme.textSecondary) {
                viewModel.clearSelection()
            }
        }
    }

    private func cutControls(_ region: ProjectedRegion) -> some View {
        HStack(spacing: AuraTheme.Space.sm) {
            Image(systemName: "scissors")
                .font(.system(size: 10))
                .foregroundStyle(ReviewPalette.cut)
            Text(region.label ?? String(format: "%.2fs cut", region.span.duration))
                .font(.system(size: 11))
                .foregroundStyle(AuraTheme.textSecondary)
                .lineLimit(1)
            action("Restore", symbol: "arrow.uturn.backward", tint: AuraTheme.accent) {
                viewModel.restoreSelectedCutRegion()
            }
        }
    }

    private func action(
        _ title: String,
        symbol: String,
        tint: Color,
        enabled: Bool = true,
        perform: @escaping () -> Void
    ) -> some View {
        Button(action: perform) {
            HStack(spacing: AuraTheme.Space.xs + 1) {
                Image(systemName: symbol).font(.system(size: 9, weight: .semibold))
                Text(title).font(.system(size: 11, weight: .medium))
            }
            .foregroundStyle(enabled ? tint : AuraTheme.textTertiary)
            .padding(.horizontal, AuraTheme.Space.sm)
            .padding(.vertical, 4)
            .background {
                RoundedRectangle(cornerRadius: 6).fill(AuraTheme.surfaceElevated)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }

    /// A jump list, because a marker outside the visible window is otherwise unreachable
    /// without hunting for it at a zoom level where it is a single pixel.
    @ViewBuilder
    private var markerMenu: some View {
        let markers = viewModel.projection.markers

        Menu {
            Button("Add Marker at Playhead") { viewModel.addMarkerAtPlayhead() }
            if !markers.isEmpty {
                Divider()
                ForEach(markers) { marker in
                    Button {
                        viewModel.seek(to: marker)
                        viewModel.revealInViewport(marker.source)
                    } label: {
                        Text("\(TimeFormatting.timecode(marker.source.seconds))  \(marker.label.isEmpty ? "Marker" : marker.label)")
                    }
                }
            }
        } label: {
            Image(systemName: "bookmark")
                .font(.system(size: 11, weight: .medium))
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .foregroundStyle(AuraTheme.textSecondary)
        .help(markers.isEmpty ? "Add a marker (M)" : "Markers (\(markers.count))")
    }

    /// Following is a toggle rather than always-on: it moves the view during playback, and a
    /// user comparing two distant parts of the recording wants it to hold still.
    private var followToggle: some View {
        Button {
            viewModel.followsPlayhead.toggle()
            if viewModel.followsPlayhead { viewModel.scrollToPlayhead() }
        } label: {
            Image(systemName: viewModel.followsPlayhead
                  ? "arrow.trianglehead.clockwise.rotate.90"
                  : "pin.slash")
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(viewModel.followsPlayhead ? AuraTheme.accent : AuraTheme.textTertiary)
                .frame(width: 26, height: 26)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(viewModel.followsPlayhead
              ? "Following the playhead — the view pages along as it plays"
              : "Not following — the view stays where you put it")
    }

    private var zoomControls: some View {
        HStack(spacing: AuraTheme.Space.xs) {
            icon("minus.magnifyingglass", help: "Zoom out (−)", enabled: viewModel.canZoomOut) {
                viewModel.zoomOut()
            }
            icon("arrow.left.and.right", help: "Fit", enabled: viewModel.canZoomOut) {
                viewModel.zoomToFit()
            }
            icon("plus.magnifyingglass", help: "Zoom in (+)", enabled: viewModel.canZoomIn) {
                viewModel.zoomIn()
            }
        }
    }

    private func icon(
        _ symbol: String,
        help: String,
        enabled: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(enabled ? AuraTheme.textSecondary : AuraTheme.textTertiary)
                .frame(width: 26, height: 26)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .help(help)
    }
}
