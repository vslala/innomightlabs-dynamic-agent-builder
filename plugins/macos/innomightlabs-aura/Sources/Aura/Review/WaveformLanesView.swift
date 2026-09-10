import SwiftUI

/// The two audio sources as separate lanes, each with its own mute, gain, and A/V slip.
///
/// Kept separate rather than mixed on purpose: it is what gives the user (and later the
/// agent) control over each source independently, and it is also what makes per-lane gain
/// expressible at all, since audio mix parameters are per composition track.
struct WaveformLanesView: View {
    @ObservedObject var viewModel: ReviewViewModel

    @State private var lastMagnification: CGFloat = 1

    private var lanes: [AudioLane] {
        AudioLane.allCases.filter { lane in
            viewModel.timeline?.audio.contains { $0.lane == lane } ?? false
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            if !lanes.isEmpty {
                Divider()
                zoomBar
            }
            ForEach(lanes, id: \.self) { lane in
                Divider()
                WaveformLaneView(viewModel: viewModel, lane: lane)
            }
        }
        .gesture(
            MagnifyGesture()
                .onChanged { value in
                    // Relative to the last delivered magnification rather than the gesture's
                    // start, so a continuous pinch zooms smoothly instead of snapping.
                    let delta = value.magnification / lastMagnification
                    lastMagnification = value.magnification
                    viewModel.setZoom(scale: delta)
                }
                .onEnded { _ in lastMagnification = 1 }
        )
    }

    private var zoomBar: some View {
        HStack(spacing: 8) {
            Text(zoomLabel)
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(.secondary)
                .frame(width: 112, alignment: .leading)

            Spacer()

            Button { viewModel.zoomOut() } label: { Image(systemName: "minus.magnifyingglass") }
                .disabled(!viewModel.canZoomOut)
                .help("Zoom out")

            Button { viewModel.zoomIn() } label: { Image(systemName: "plus.magnifyingglass") }
                .disabled(!viewModel.canZoomIn)
                .help("Zoom in around the playhead")

            Button("Fit") { viewModel.zoomToFit() }
                .disabled(!viewModel.canZoomOut)
        }
        .buttonStyle(.borderless)
        .padding(.horizontal, 10)
        .padding(.vertical, 4)
    }

    private var zoomLabel: String {
        guard viewModel.visibleDuration != nil else { return "Whole recording" }
        let span = viewModel.visibleSpan
        return "\(TimeFormatting.timecode(span.start)) +\(String(format: "%.2fs", span.duration))"
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
            VStack(alignment: .leading, spacing: 3) {
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

                    // Local while dragging, committed on release — every commit is an undo
                    // step, an `edit.json` write, and a full composition rebuild.
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
                    .frame(width: 66)
                }

                slipControl
            }
            .frame(width: 148, alignment: .leading)

            WaveformCanvas(
                peaks: viewModel.peaks[lane],
                visibleSpan: viewModel.visibleSpan,
                timeline: viewModel.timeline,
                laneOffset: viewModel.automaticCorrection(for: lane) + viewModel.laneOffset(lane),
                playhead: Timeline.seconds(viewModel.playhead),
                isMuted: isMuted,
                onSeek: { viewModel.commitScrub(to: $0) },
                onScrub: { viewModel.scrub(to: $0) }
            )
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .frame(maxHeight: .infinity)
    }

    /// Fine A/V slip. The automatic correction from the recorded track start offsets is
    /// applied already; this is the residual nudge, and the only way to fix a recording made
    /// before those offsets were logged.
    private var slipControl: some View {
        let manual = viewModel.laneOffset(lane)
        let automatic = viewModel.automaticCorrection(for: lane)

        return HStack(spacing: 3) {
            Text("sync")
                .font(.system(size: 9))
                .foregroundStyle(.tertiary)

            Button { viewModel.nudgeLaneOffset(lane, by: -0.01) } label: { Image(systemName: "minus") }
                .buttonStyle(.borderless)
                .help("Play \(title) 10ms earlier")

            Text(String(format: "%+.0fms", manual * 1000))
                .font(.system(size: 9, design: .monospaced))
                .frame(width: 42)
                .foregroundStyle(manual == 0 ? .tertiary : .primary)

            Button { viewModel.nudgeLaneOffset(lane, by: 0.01) } label: { Image(systemName: "plus") }
                .buttonStyle(.borderless)
                .help("Play \(title) 10ms later")

            if manual != 0 {
                Button { viewModel.resetLaneOffset(lane) } label: { Image(systemName: "arrow.counterclockwise") }
                    .buttonStyle(.borderless)
                    .help("Clear the manual slip")
            }
        }
        .help(automatic > 0
              ? String(format: "%.0fms of startup delay was corrected automatically", automatic * 1000)
              : "No recorded start offset for this track — slip it by hand if it sounds late or early")
    }
}

struct WaveformCanvas: View {
    let peaks: WaveformPeaks?
    let visibleSpan: TimeSpan
    let timeline: ResolvedTimeline?
    /// Where this lane's audio sits relative to the composition, so the drawn waveform lines
    /// up with what is actually heard rather than with the raw file.
    let laneOffset: TimeInterval
    let playhead: TimeInterval
    let isMuted: Bool
    let onSeek: (TimeInterval) -> Void
    let onScrub: (TimeInterval) -> Void

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                // Free of the playhead and Equatable, so SwiftUI can skip re-rasterizing it.
                // While zoomed the window follows the playhead so it does redraw, but when
                // fitted to the whole recording — the common case — it is drawn once.
                WaveformTrace(
                    peaks: peaks,
                    visibleSpan: visibleSpan,
                    timeline: timeline,
                    laneOffset: laneOffset,
                    isMuted: isMuted
                )
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
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { onScrub(time(at: $0.location.x, width: geometry.size.width)) }
                    .onEnded { onSeek(time(at: $0.location.x, width: geometry.size.width)) }
            )
        }
    }

    private func time(at x: CGFloat, width: CGFloat) -> TimeInterval {
        guard width > 0 else { return visibleSpan.start }
        let fraction = min(1, max(0, Double(x / width)))
        return visibleSpan.start + fraction * visibleSpan.duration
    }

    private func playheadOffset(width: CGFloat) -> CGFloat {
        guard visibleSpan.duration > 0 else { return 0 }
        let fraction = (playhead - visibleSpan.start) / visibleSpan.duration
        return min(width, max(0, width * fraction))
    }
}

/// Draws a peak envelope over a window of the **composition** timeline.
///
/// The cached peaks are indexed by time in the audio file, so each column is mapped back
/// through the time map and then through this lane's offset. That is what keeps the waveform
/// in step with the video both after a cut and after an A/V slip.
struct WaveformTrace: View, Equatable {
    let peaks: WaveformPeaks?
    let visibleSpan: TimeSpan
    let timeline: ResolvedTimeline?
    let laneOffset: TimeInterval
    let isMuted: Bool

    var body: some View {
        Canvas { context, size in
            guard
                let peaks, peaks.bucketCount > 0,
                let timeline, timeline.duration > .zero,
                visibleSpan.duration > 0
            else { return }

            let midY = size.height / 2
            var path = Path()

            for column in 0..<Int(size.width) {
                let compositionTime = visibleSpan.start
                    + Double(column) / Double(size.width) * visibleSpan.duration
                guard let source = timeline.timeMap.sourceTime(forComposition: compositionTime) else { continue }

                // Composition -> session -> this file's own timeline.
                let fileTime = source - laneOffset
                let bucket = Int(fileTime * Double(peaks.bucketsPerSecond))
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
