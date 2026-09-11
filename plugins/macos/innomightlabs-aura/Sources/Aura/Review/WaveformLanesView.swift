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

            Divider().frame(height: 12)

            Picker("", selection: Binding(
                get: { viewModel.waveformScale },
                set: { viewModel.setWaveformScale($0) }
            )) {
                ForEach(WaveformScale.allCases, id: \.self) { option in
                    Text(option.label).tag(option)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(width: 116)
            .help("Speech has too wide a dynamic range for a linear axis; dB spends the lane's height where the audio actually is")
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
                detail: viewModel.laneDetail[lane],
                detailSpan: viewModel.laneDetailSpan,
                visibleSpan: viewModel.visibleSpan,
                timeline: viewModel.timeline,
                laneOffset: viewModel.automaticCorrection(for: lane) + viewModel.laneOffset(lane),
                playhead: Timeline.seconds(viewModel.playhead),
                isMuted: isMuted,
                onSeek: { viewModel.commitScrub(to: $0) },
                onScrub: { viewModel.scrub(to: $0) },
                onNeedsDetail: { viewModel.requestWaveformDetail(viewWidth: $0) },
                scale: viewModel.waveformScale
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
    /// Higher-resolution peaks for the zoomed window, when the cache is too coarse to draw.
    let detail: WaveformPeaks?
    let detailSpan: TimeSpan?
    let visibleSpan: TimeSpan
    let timeline: ResolvedTimeline?
    /// Where this lane's audio sits relative to the composition, so the drawn waveform lines
    /// up with what is actually heard rather than with the raw file.
    let laneOffset: TimeInterval
    let playhead: TimeInterval
    let isMuted: Bool
    let onSeek: (TimeInterval) -> Void
    let onScrub: (TimeInterval) -> Void
    let onNeedsDetail: (CGFloat) -> Void
    let scale: WaveformScale

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                // Free of the playhead and Equatable, so SwiftUI can skip re-rasterizing it.
                // While zoomed the window follows the playhead so it does redraw, but when
                // fitted to the whole recording — the common case — it is drawn once.
                WaveformTrace(
                    peaks: usableDetail ?? peaks,
                    // Detail peaks are already relative to their own window, so the trace is
                    // told where they start instead of mapping them through the whole file.
                    peaksStart: usableDetail == nil ? 0 : (detailSpan?.start ?? 0),
                    visibleSpan: visibleSpan,
                    timeline: timeline,
                    laneOffset: usableDetail == nil ? laneOffset : 0,
                    isMuted: isMuted,
                    scale: scale
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
            .onAppear { onNeedsDetail(geometry.size.width) }
            .onChange(of: visibleSpan) { _, _ in onNeedsDetail(geometry.size.width) }
            .onChange(of: geometry.size.width) { _, width in onNeedsDetail(width) }
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { onScrub(time(at: $0.location.x, width: geometry.size.width)) }
                    .onEnded { onSeek(time(at: $0.location.x, width: geometry.size.width)) }
            )
        }
    }

    /// Detail is only usable while it covers the window being drawn; otherwise the cached
    /// envelope is shown until the new read lands, rather than a torn mixture.
    private var usableDetail: WaveformPeaks? {
        guard let detail, let detailSpan else { return nil }
        guard detailSpan.start <= visibleSpan.start + 0.001,
              detailSpan.end >= visibleSpan.end - 0.001 else { return nil }
        return detail
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
    /// Time the first bucket corresponds to. Zero for the whole-file cache; the window's
    /// start for a detail read.
    let peaksStart: TimeInterval
    let visibleSpan: TimeSpan
    let timeline: ResolvedTimeline?
    let laneOffset: TimeInterval
    let isMuted: Bool
    let scale: WaveformScale

    /// One column's worth of the envelope.
    private struct Column {
        let x: Double
        let peakTop: Double
        let peakBottom: Double
        let rmsTop: Double
        let rmsBottom: Double
    }

    var body: some View {
        Canvas { context, size in
            guard
                let peaks, peaks.bucketCount > 0,
                let timeline, timeline.duration > .zero,
                visibleSpan.duration > 0
            else { return }

            let midY = size.height / 2
            let columns = columns(peaks: peaks, timeline: timeline, size: size, midY: midY)
            guard !columns.isEmpty else { return }

            // Two filled bands, the way Audacity draws it: a light outer envelope of the
            // extremes, and a solid inner band of RMS. The peaks alone are spiky and say
            // little about where speech actually is; the RMS body is what makes it readable.
            let colour: Color = isMuted ? .secondary : .accentColor
            context.fill(
                band(columns, top: \.peakTop, bottom: \.peakBottom, midY: midY),
                with: .color(colour.opacity(isMuted ? 0.2 : 0.45))
            )
            context.fill(
                band(columns, top: \.rmsTop, bottom: \.rmsBottom, midY: midY),
                with: .color(colour.opacity(isMuted ? 0.35 : 0.95))
            )

            // Centre line, so silence still reads as a lane rather than as nothing.
            var centre = Path()
            centre.move(to: CGPoint(x: 0, y: midY))
            centre.addLine(to: CGPoint(x: size.width, y: midY))
            context.stroke(centre, with: .color(colour.opacity(0.5)), lineWidth: 0.5)
        }
    }

    private func columns(
        peaks: WaveformPeaks,
        timeline: ResolvedTimeline,
        size: CGSize,
        midY: Double
    ) -> [Column] {
        var result: [Column] = []
        result.reserveCapacity(Int(size.width))

        for column in 0..<Int(size.width) {
            let compositionTime = visibleSpan.start
                + Double(column) / Double(size.width) * visibleSpan.duration
            guard let source = timeline.timeMap.sourceTime(forComposition: compositionTime) else { continue }

            // Composition -> session -> this file's own timeline, then into the bucket
            // array's own origin.
            let fileTime = source - laneOffset
            let bucket = Int((fileTime - peaksStart) * Double(peaks.bucketsPerSecond))
            guard bucket >= 0, bucket < peaks.bucketCount, peaks.coverage[bucket] else { continue }

            let high = scale.fraction(peaks.maxima[bucket])
            let low = scale.fraction(peaks.minima[bucket])
            let loudness = scale.fraction(peaks.rms[bucket])

            result.append(Column(
                x: Double(column) + 0.5,
                peakTop: midY - midY * max(high, 0),
                peakBottom: midY - midY * min(low, 0),
                rmsTop: midY - midY * loudness,
                rmsBottom: midY + midY * loudness
            ))
        }
        return result
    }

    /// A filled ribbon: along the top edge, then back along the bottom.
    ///
    /// Every column is given at least a hairline of height so a quiet-but-present stretch
    /// still draws as a line rather than disappearing — the difference between "silent" and
    /// "quiet" matters when deciding where to cut.
    private func band(
        _ columns: [Column],
        top: KeyPath<Column, Double>,
        bottom: KeyPath<Column, Double>,
        midY: Double
    ) -> Path {
        var path = Path()
        guard let first = columns.first else { return path }

        path.move(to: CGPoint(x: first.x, y: min(first[keyPath: top], midY - 0.25)))
        for column in columns {
            path.addLine(to: CGPoint(x: column.x, y: min(column[keyPath: top], midY - 0.25)))
        }
        for column in columns.reversed() {
            path.addLine(to: CGPoint(x: column.x, y: max(column[keyPath: bottom], midY + 0.25)))
        }
        path.closeSubpath()
        return path
    }
}
