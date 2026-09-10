import SwiftUI

/// The two audio sources as separate lanes, each with its own mute and gain.
///
/// Kept separate rather than mixed on purpose: it is what gives the user (and later the
/// agent) control over each source independently, and it is also what makes per-lane gain
/// expressible at all, since audio mix parameters are per composition track.
struct WaveformLanesView: View {
    @ObservedObject var viewModel: ReviewViewModel

    var body: some View {
        VStack(spacing: 0) {
            ForEach(AudioLane.allCases, id: \.self) { lane in
                if viewModel.timeline?.audio.contains(where: { $0.lane == lane }) == true {
                    Divider()
                    WaveformLaneView(viewModel: viewModel, lane: lane)
                }
            }
        }
    }
}

struct WaveformLaneView: View {
    @ObservedObject var viewModel: ReviewViewModel
    let lane: AudioLane

    @State private var draftGain: Double?

    private var title: String {
        switch lane {
        case .microphone: return "Microphone"
        case .systemAudio: return "System Audio"
        }
    }

    private var isMuted: Bool {
        viewModel.store?.document.settings(for: lane).muted ?? false
    }

    private var gain: Double {
        viewModel.store?.document.gain(for: lane, at: viewModel.playheadSourceTime) ?? 1
    }

    var body: some View {
        HStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                HStack(spacing: 4) {
                    Button {
                        viewModel.setLaneMuted(lane, !isMuted)
                    } label: {
                        Image(systemName: isMuted ? "speaker.slash.fill" : "speaker.wave.2.fill")
                    }
                    .buttonStyle(.borderless)
                    .help(isMuted ? "Unmute \(title)" : "Mute \(title)")

                    // Local while dragging, committed on release — same reason as the
                    // camera overlay: every commit is an undo step, an `edit.json` write,
                    // and a full composition rebuild with a player-item swap.
                    Slider(
                        value: Binding(
                            get: { draftGain ?? gain },
                            set: { draftGain = $0 }
                        ),
                        in: 0...1,
                        onEditingChanged: { editing in
                            guard !editing, let committed = draftGain else { return }
                            draftGain = nil
                            if committed != gain {
                                viewModel.setLaneGain(lane, committed)
                            }
                        }
                    )
                    .disabled(isMuted)
                    .frame(width: 70)
                }
            }
            .frame(width: 120, alignment: .leading)

            WaveformCanvas(
                peaks: viewModel.peaks[lane],
                timeline: viewModel.timeline,
                playhead: Timeline.seconds(viewModel.playhead),
                isMuted: isMuted
            )
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .frame(maxHeight: .infinity)
    }
}

struct WaveformCanvas: View {
    let peaks: WaveformPeaks?
    let timeline: ResolvedTimeline?
    let playhead: TimeInterval
    let isMuted: Bool

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                // Equatable and free of the playhead, so SwiftUI skips re-rasterizing the
                // trace on every tick — the playhead moves 30 times a second and the
                // waveform underneath it does not change at all.
                WaveformTrace(peaks: peaks, timeline: timeline, isMuted: isMuted)
                    .equatable()

                if peaks == nil {
                    ProgressView()
                        .controlSize(.small)
                        .frame(maxWidth: .infinity)
                }

                Rectangle()
                    .fill(.primary)
                    .frame(width: 1)
                    .offset(x: playheadOffset(width: geometry.size.width))
            }
            .background(.quaternary.opacity(0.35))
        }
    }

    private func playheadOffset(width: CGFloat) -> CGFloat {
        guard let timeline, timeline.duration > .zero else { return 0 }
        let fraction = playhead / Timeline.seconds(timeline.duration)
        return min(width, max(0, width * fraction))
    }
}

/// Draws a peak envelope along the **composition** timeline.
///
/// The cached peaks are indexed by source time, so each column is mapped back through the
/// time map. That keeps the waveform in step with the video after a cut instead of drifting
/// by the length of everything removed.
struct WaveformTrace: View, Equatable {
    let peaks: WaveformPeaks?
    let timeline: ResolvedTimeline?
    let isMuted: Bool

    var body: some View {
        Canvas { context, size in
            guard
                let peaks, peaks.bucketCount > 0,
                let timeline, timeline.duration > .zero
            else { return }

            let duration = Timeline.seconds(timeline.duration)
            let midY = size.height / 2
            var path = Path()

            for column in 0..<Int(size.width) {
                let compositionTime = Double(column) / Double(size.width) * duration
                guard let source = timeline.timeMap.sourceTime(forComposition: compositionTime) else { continue }

                let bucket = Int(source * Double(peaks.bucketsPerSecond))
                guard bucket >= 0, bucket < peaks.bucketCount, peaks.coverage[bucket] else { continue }

                let x = Double(column) + 0.5
                let top = midY - midY * Double(peaks.maxima[bucket])
                let bottom = midY - midY * Double(peaks.minima[bucket])
                path.move(to: CGPoint(x: x, y: min(top, bottom)))
                path.addLine(to: CGPoint(x: x, y: max(bottom, top) + 0.5))
            }

            context.stroke(
                path,
                with: .color(isMuted ? .secondary.opacity(0.35) : .accentColor.opacity(0.8)),
                lineWidth: 1
            )
        }
    }
}
