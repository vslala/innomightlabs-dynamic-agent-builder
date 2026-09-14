import SwiftUI

/// Transport under the preview. Deliberately quiet: no borders, no permanent toolbar, and the
/// secondary group (resolution, speed, fullscreen) appears only on hover.
struct PreviewControlsView: View {
    @ObservedObject var viewModel: ReviewViewModel
    let onToggleFullScreen: () -> Void

    @State private var isHovering = false

    var body: some View {
        ZStack {
            transport

            HStack {
                timecode
                Spacer()
                secondary
                    .opacity(isHovering ? 1 : 0)
                    // Kept in the layout when hidden, so the transport does not shift as the
                    // pointer arrives.
                    .allowsHitTesting(isHovering)
            }
        }
        .padding(.horizontal, AuraTheme.Space.md)
        .frame(height: 56)
        .background(AuraTheme.surface)
        .onHover { isHovering = $0 }
    }

    private var transport: some View {
        HStack(spacing: AuraTheme.Space.lg) {
            iconButton("backward.end.fill", size: 13, help: "Previous cut") {
                viewModel.stepToPreviousBoundary()
            }

            Button {
                viewModel.togglePlayback()
            } label: {
                Image(systemName: viewModel.isPlaying ? "pause.fill" : "play.fill")
                    .font(.system(size: 19))
                    .foregroundStyle(AuraTheme.textPrimary)
                    .frame(width: 42, height: 34)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help(viewModel.isPlaying ? "Pause (Space)" : "Play (Space)")

            iconButton("forward.end.fill", size: 13, help: "Next cut") {
                viewModel.stepToNextBoundary()
            }
        }
    }

    private var timecode: some View {
        Text("\(TimeFormatting.timecode(Timeline.seconds(viewModel.playhead))) / \(TimeFormatting.timecode(Timeline.seconds(viewModel.duration)))")
            .font(.system(size: 11, design: .monospaced))
            .foregroundStyle(AuraTheme.textSecondary)
    }

    private var secondary: some View {
        HStack(spacing: AuraTheme.Space.sm) {
            if viewModel.canChangeLayout {
                LayoutModeMenu(viewModel: viewModel)
            }

            Menu {
                ForEach(PlaybackRate.allCases) { rate in
                    Button(rate.title) { viewModel.setPlaybackRate(rate) }
                }
            } label: {
                Text(viewModel.playbackRate.title)
                    .font(.system(size: 11, weight: .medium))
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .foregroundStyle(AuraTheme.textSecondary)
            .help("Playback speed")

            // Meaningless without video: a podcast has no frame to fill the screen with.
            if viewModel.hasVideo {
                iconButton("arrow.up.left.and.arrow.down.right", size: 11, help: "Full screen") {
                    onToggleFullScreen()
                }
            }
        }
    }

    private func iconButton(
        _ symbol: String,
        size: CGFloat,
        help: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: size, weight: .medium))
                .foregroundStyle(AuraTheme.textSecondary)
                .frame(width: 28, height: 28)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(help)
    }
}

/// The rates the speed menu offers, and the J/K/L shuttle steps through.
enum PlaybackRate: Double, CaseIterable, Identifiable, Sendable {
    case quarter = 0.25
    case half = 0.5
    case normal = 1
    case double = 2
    case quadruple = 4

    var id: Double { rawValue }

    var title: String {
        switch self {
        case .quarter: return "0.25x"
        case .half: return "0.5x"
        case .normal: return "1x"
        case .double: return "2x"
        case .quadruple: return "4x"
        }
    }

    /// The next rung up the ladder, saturating at the top so repeated `L` does not wrap back
    /// to slow motion.
    var faster: PlaybackRate {
        let ladder = PlaybackRate.allCases
        guard let index = ladder.firstIndex(of: self), index + 1 < ladder.count else { return self }
        return ladder[index + 1]
    }
}

struct LayoutModeMenu: View {
    @ObservedObject var viewModel: ReviewViewModel

    var body: some View {
        Menu {
            ForEach(LayoutMode.allCases) { mode in
                Button {
                    viewModel.setLayoutMode(mode)
                } label: {
                    Label(mode.title, systemImage: mode.symbol)
                }
            }
            Text("Applies from the playhead onwards")

            Divider()

            // Style is a property of the whole recording, not a keyframe, so it is separated
            // from the modes above rather than listed alongside them.
            Section("Camera style") {
                CameraStyleMenu(viewModel: viewModel)
            }
        } label: {
            Image(systemName: viewModel.layoutMode.symbol)
                .font(.system(size: 12, weight: .medium))
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .foregroundStyle(AuraTheme.textSecondary)
        .help("Layout — \(viewModel.layoutMode.title)")
    }
}
