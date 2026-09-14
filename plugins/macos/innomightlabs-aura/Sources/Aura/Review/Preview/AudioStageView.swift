import SwiftUI

/// The stage for a recording with no video: the audio lanes at full height.
///
/// Shares `viewModel.visibleSpan` with the timeline rather than owning a second viewport —
/// zooming the timeline zooms this, and a selection made here is the same selection. What this
/// adds over the timeline's 44pt lane is height: cut boundaries and speech onsets are placeable
/// by eye at well over 100pt in a way they are not at 44.
struct AudioStageView: View {
    @ObservedObject var viewModel: ReviewViewModel

    private var lanes: [AudioLane] {
        AudioLane.allCases.filter { lane in
            viewModel.timeline?.audio.contains { $0.lane == lane } ?? false
        }
    }

    private var window: StampSpan<Source> { viewModel.visibleSpan }

    var body: some View {
        Group {
            if lanes.isEmpty {
                emptyState
            } else {
                SourceAxisSurface(viewModel: viewModel, window: window) { width in
                    VStack(alignment: .leading, spacing: AuraTheme.Space.lg) {
                        ForEach(lanes, id: \.self) { lane in
                            laneStack(lane, width: width)
                        }
                    }
                }
            }
        }
        .padding(AuraTheme.Space.md)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AuraTheme.background)
    }

    private func laneStack(_ lane: AudioLane, width: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: AuraTheme.Space.xs) {
            HStack(spacing: AuraTheme.Space.sm) {
                Image(systemName: laneSymbol(lane))
                    .font(.system(size: 11))
                    .foregroundStyle(AuraTheme.textSecondary)
                Text(laneTitle(lane))
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(AuraTheme.textSecondary)
            }

            AudioLaneWaveform(viewModel: viewModel, lane: lane, height: laneHeight)
        }
        .frame(width: width)
    }

    /// Two lanes share the stage; one gets the whole thing.
    private var laneHeight: CGFloat { lanes.count > 1 ? 150 : 240 }

    private func laneTitle(_ lane: AudioLane) -> String {
        lane == .microphone ? TimelineLane.voice.title : TimelineLane.systemAudio.title
    }

    private func laneSymbol(_ lane: AudioLane) -> String {
        lane == .microphone ? TimelineLane.voice.symbol : TimelineLane.systemAudio.symbol
    }

    private var emptyState: some View {
        Text("No audio in this recording.")
            .font(.system(size: 13))
            .foregroundStyle(AuraTheme.textSecondary)
    }
}
