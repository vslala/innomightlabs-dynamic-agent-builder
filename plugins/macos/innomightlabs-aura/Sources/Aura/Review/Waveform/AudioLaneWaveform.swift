import SwiftUI

/// One audio lane's waveform, at whatever height the caller gives it. Used at 44pt inside
/// `TimelineView`'s lane stack, and at full stage height inside `AudioStageView` for a
/// recording with no video.
struct AudioLaneWaveform: View {
    @ObservedObject var viewModel: ReviewViewModel
    let lane: AudioLane
    let height: CGFloat

    private var isMuted: Bool {
        viewModel.store?.document.settings(for: lane).muted ?? false
    }

    /// Detail is only usable while it covers the window being drawn; otherwise the cached
    /// envelope keeps drawing until the finer read lands, rather than a torn mixture.
    private var usableDetail: WaveformPeaks? {
        guard let detail = viewModel.laneDetail[lane], let span = viewModel.laneDetailSpan else { return nil }
        guard span.start <= viewModel.visibleSpan.start, span.end >= viewModel.visibleSpan.end else { return nil }
        return detail
    }

    var body: some View {
        WaveformTrace(
            peaks: usableDetail ?? viewModel.peaks[lane],
            // Both branches are source time, derived rather than hand-signed.
            peaksStart: usableDetail == nil
                ? viewModel.projection.sourceTime(forAudioFile: 0, lane: lane)
                : (viewModel.laneDetailSpan?.start ?? .zero),
            window: viewModel.visibleSpan,
            isMuted: isMuted,
            scale: viewModel.waveformScale
        )
        .equatable()
        .frame(height: height)
        .background {
            RoundedRectangle(cornerRadius: AuraTheme.Radius.sm)
                .fill(AuraTheme.surfaceElevated)
        }
        .clipShape(RoundedRectangle(cornerRadius: AuraTheme.Radius.sm))
        .overlay {
            if viewModel.peaks[lane] == nil {
                ProgressView().controlSize(.small)
            }
        }
    }
}
