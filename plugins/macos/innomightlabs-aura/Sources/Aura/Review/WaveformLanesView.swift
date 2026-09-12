import SwiftUI

/// The audio lanes: the whole recording, to scale, with cut regions shaded.
///
/// The axis is the **recording's**, not the edited timeline's, because that is the only way a
/// cut can be seen at all — on the edited timeline the cut audio is simply absent. The
/// consequence is that the playhead jumps over cuts during playback, and the window stays
/// where the user put it rather than chasing it.
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
                toolbar
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

    private var toolbar: some View {
        HStack(spacing: 8) {
            Text(windowLabel)
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(.secondary)
                .frame(width: 132, alignment: .leading)

            if let selection = viewModel.selection {
                selectionControls(selection)
            } else if let region = viewModel.selectedCutRegion {
                cutControls(region)
            }

            Spacer()

            Button { viewModel.splitAtPlayhead() } label: {
                Image(systemName: "square.split.2x1")
            }
            .help("Split at the playhead (S)")

            Button { viewModel.addMarkerAtPlayhead() } label: {
                Image(systemName: "bookmark")
            }
            .help("Add a marker at the playhead (M)")

            markerMenu

            Divider().frame(height: 12)

            if !viewModel.isPlayheadVisible, viewModel.visibleDuration != nil {
                Button("Playhead") { viewModel.scrollToPlayhead() }
                    .help("Scroll to the playhead — the view stays put during playback on purpose")
            }

            Button { viewModel.zoomOut() } label: { Image(systemName: "minus.magnifyingglass") }
                .disabled(!viewModel.canZoomOut)
            Button { viewModel.zoomIn() } label: { Image(systemName: "plus.magnifyingglass") }
                .disabled(!viewModel.canZoomIn)
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

    /// A jump list, because a marker outside the visible window is otherwise unreachable
    /// without hunting for it at a zoom level where it is a single pixel.
    @ViewBuilder
    private var markerMenu: some View {
        let markers = viewModel.projection.markers

        Menu {
            if markers.isEmpty {
                Text("No markers")
            } else {
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
            Image(systemName: "list.bullet")
        }
        .menuIndicator(.hidden)
        .fixedSize()
        .help(markers.isEmpty ? "No markers yet" : "Go to a marker (\(markers.count))")
    }

    private var windowLabel: String {
        let span = viewModel.visibleSpan
        guard viewModel.visibleDuration != nil else { return "Whole recording" }
        return "\(TimeFormatting.timecode(span.start.seconds)) +\(String(format: "%.2fs", span.duration))"
    }

    /// A selection reports both its span and how much of it survives: after cuts the two
    /// differ, and the difference is easy to misjudge.
    private func selectionControls(_ selection: StampSpan<Source>) -> some View {
        let kept = viewModel.projection.keptDuration(in: selection)

        return HStack(spacing: 6) {
            Text(String(format: "%.2fs selected", selection.duration))
                .font(.caption)
            if abs(kept - selection.duration) > 0.005 {
                Text(String(format: "(%.2fs kept)", kept))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Button("Delete", systemImage: "scissors") { viewModel.cutSelection() }
                .disabled(kept <= 0)
            Button("Split", systemImage: "square.split.2x1") { viewModel.splitAtSelectionStart() }
            Button("Clear") { viewModel.clearSelection() }
        }
        .font(.caption)
    }

    private func cutControls(_ region: ProjectedRegion) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "scissors")
                .foregroundStyle(ReviewPalette.cut)
            Text(region.label ?? String(format: "%.2fs cut", region.span.duration))
                .font(.caption)
                .lineLimit(1)
            Button("Restore") { viewModel.restoreSelectedCutRegion() }
        }
        .font(.caption)
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

            WaveformCanvas(viewModel: viewModel, lane: lane, isMuted: isMuted)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .frame(maxHeight: .infinity)
    }

    /// Fine A/V slip. The automatic correction from the recorded track start offsets is
    /// applied already; this is the residual nudge.
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

/// One lane's drawing surface and gestures.
struct WaveformCanvas: View {
    @ObservedObject var viewModel: ReviewViewModel
    let lane: AudioLane
    let isMuted: Bool

    /// Set while a drag is building a selection, so a click can be told from a drag.
    @State private var dragOrigin: Stamp<Source>?
    /// Where a marker is being dragged to, so it tracks the cursor before the edit commits.
    /// Transient — it never reaches the document until the drag ends.
    @State private var draggingMarker: (id: String, stamp: Stamp<Source>)?

    private var window: StampSpan<Source> { viewModel.visibleSpan }

    var body: some View {
        GeometryReader { geometry in
            let width = geometry.size.width

            ZStack(alignment: .leading) {
                WaveformTrace(
                    peaks: usableDetail ?? viewModel.peaks[lane],
                    // Both branches are source time, derived rather than hand-signed.
                    peaksStart: usableDetail == nil
                        ? viewModel.projection.sourceTime(forAudioFile: 0, lane: lane)
                        : (viewModel.laneDetailSpan?.start ?? .zero),
                    window: window,
                    isMuted: isMuted,
                    scale: viewModel.waveformScale
                )
                .equatable()

                if viewModel.peaks[lane] == nil {
                    ProgressView().controlSize(.small).frame(maxWidth: .infinity)
                }

                cutRegions(width: width)
                splits(width: width)
                selectionOverlay(width: width)
                markers(width: width)
                playhead(width: width)
            }
            .background(.quaternary.opacity(0.35))
            .contentShape(Rectangle())
            .onAppear { viewModel.requestWaveformDetail(viewWidth: width) }
            .onChange(of: window) { _, _ in viewModel.requestWaveformDetail(viewWidth: width) }
            .onChange(of: width) { _, new in viewModel.requestWaveformDetail(viewWidth: new) }
            .gesture(dragGesture(width: width))
            // Simultaneous, so a single click still reaches the drag gesture above. Spatial
            // because restoring needs to know *which* cut was clicked, and a plain
            // `TapGesture` reports no location.
            .simultaneousGesture(
                SpatialTapGesture(count: 2)
                    .onEnded { value in
                        viewModel.restoreCutRegion(at: stamp(atX: value.location.x, width: width))
                    }
            )
        }
    }

    // MARK: - Layers

    /// Cut regions, shaded in the same colour as a struck-through word.
    private func cutRegions(width: CGFloat) -> some View {
        ForEach(viewModel.projection.regions.filter { $0.isCut && $0.span.overlaps(window) }) { region in
            let start = window.fraction(of: region.span.start) * width
            let end = window.fraction(of: region.span.end) * width
            let selected = viewModel.selectedCutRegionID == region.id

            Rectangle()
                .fill(ReviewPalette.cut.opacity(selected ? 0.38 : 0.22))
                .overlay(alignment: .leading) {
                    Rectangle().fill(ReviewPalette.cut.opacity(0.7)).frame(width: 1)
                }
                .overlay(alignment: .trailing) {
                    Rectangle().fill(ReviewPalette.cut.opacity(0.7)).frame(width: 1)
                }
                // At least a hairline, so a 100ms word cut is still visible when the whole
                // recording is on screen.
                .frame(width: max(2, end - start))
                .offset(x: start)
                // Deliberately NOT interactive. A gesture on this rectangle — even a
                // double-tap — is a descendant of the canvas's drag gesture and outranks it,
                // which silently killed click-to-select on exactly the regions the toolbar's
                // Restore button needs selected. Double-click is handled on the canvas
                // instead, where it can coexist with the drag.
                .allowsHitTesting(false)
                .help(region.label.map { "Cut: \($0) — double-click to restore" }
                      ?? "Cut — double-click to restore")
        }
    }

    /// Editorial markers on the source axis, where they can be dragged. The ruler shows the
    /// same markers on the edited timeline, but a marker inside a cut has no position there.
    private func markers(width: CGFloat) -> some View {
        ForEach(viewModel.projection.markers.filter {
            // The marker under the cursor always stays in the list. Dropping it because its
            // live position left the window would destroy the view mid-drag, so `onEnded`
            // would never fire and `draggingMarker` would be stranded for good.
            draggingMarker?.id == $0.id || window.contains($0.source)
        }) { marker in
            let live = draggingMarker?.id == marker.id ? draggingMarker!.stamp : marker.source
            let x = window.fraction(of: live) * width

            Rectangle()
                .fill(marker.isEditorial ? ReviewPalette.editorialMarker : ReviewPalette.recordingMarker)
                .frame(width: 1)
                .overlay(alignment: .top) {
                    Image(systemName: marker.isEditorial ? "bookmark.fill" : "flag.fill")
                        .font(.system(size: 7))
                        .foregroundStyle(marker.isEditorial
                                         ? ReviewPalette.editorialMarker
                                         : ReviewPalette.recordingMarker)
                }
                .frame(width: 9)
                .contentShape(Rectangle())
                .offset(x: x - 4.5)
                .help(marker.label.isEmpty ? "Marker" : marker.label)
                .highPriorityGesture(markerDrag(marker, width: width))
        }
    }

    /// Only editorial markers move. A recording marker is a fact from `events.jsonl`, so
    /// dragging one would be falsifying the record rather than editing.
    ///
    /// Uses `translation`, not `location`. The gesture is attached to the 9pt marker glyph, so
    /// `DragGesture`'s default `.local` space measures from *that* view's origin — dividing it
    /// by the canvas width put every drag within a fraction of the window's left edge. A
    /// translation is a delta, so it is independent of which view the gesture hangs on.
    private func markerDrag(_ marker: ProjectedMarker, width: CGFloat) -> some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                guard marker.isEditorial, width > 0 else { return }
                draggingMarker = (marker.id, dragged(marker, by: value.translation.width, width: width))
            }
            .onEnded { value in
                defer { draggingMarker = nil }
                guard marker.isEditorial, width > 0 else { return }
                viewModel.moveMarker(marker, to: dragged(marker, by: value.translation.width, width: width))
            }
    }

    /// The marker's own position shifted by a pixel delta, clamped to the recording.
    private func dragged(_ marker: ProjectedMarker, by dx: CGFloat, width: CGFloat) -> Stamp<Source> {
        let seconds = marker.source.seconds + Double(dx / width) * window.duration
        return Stamp(min(max(0, seconds), viewModel.recordingDuration))
    }

    private func splits(width: CGFloat) -> some View {
        ForEach(viewModel.projection.splits.filter { window.contains($0) }, id: \.seconds) { split in
            Rectangle()
                .fill(ReviewPalette.split)
                .frame(width: 1)
                .offset(x: window.fraction(of: split) * width)
        }
    }

    @ViewBuilder
    private func selectionOverlay(width: CGFloat) -> some View {
        if let selection = viewModel.selection, selection.overlaps(window) {
            let start = window.fraction(of: selection.start) * width
            let end = window.fraction(of: selection.end) * width

            Rectangle()
                .fill(ReviewPalette.selection.opacity(0.2))
                .overlay {
                    Rectangle().stroke(ReviewPalette.selection.opacity(0.8), lineWidth: 1)
                }
                .frame(width: max(1, end - start))
                .offset(x: start)
        }
    }

    @ViewBuilder
    private func playhead(width: CGFloat) -> some View {
        if let source = viewModel.projection.sourceTime(forComposition: Stamp(viewModel.playhead)),
           window.contains(source) {
            Rectangle()
                .fill(.primary)
                .frame(width: 1)
                .offset(x: window.fraction(of: source) * width)
        }
    }

    // MARK: - Gestures

    /// A drag builds a selection; a click without movement seeks, selects a cut region, or
    /// clears the selection.
    private func dragGesture(width: CGFloat) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { value in
                let origin = dragOrigin ?? stamp(atX: value.startLocation.x, width: width)
                dragOrigin = origin
                let current = stamp(atX: value.location.x, width: width)

                if abs(value.translation.width) > 3 {
                    viewModel.select(from: origin, to: current)
                }
            }
            .onEnded { value in
                defer { dragOrigin = nil }
                let stamp = self.stamp(atX: value.location.x, width: width)

                guard abs(value.translation.width) <= 3 else {
                    viewModel.select(from: dragOrigin ?? stamp, to: stamp)
                    return
                }
                viewModel.handleLaneClick(at: stamp)
            }
    }

    private func stamp(atX x: CGFloat, width: CGFloat) -> Stamp<Source> {
        guard width > 0 else { return window.start }
        return window.stamp(atFraction: Double(x / width))
    }

    /// Detail is only usable while it covers the window being drawn; otherwise the cached
    /// envelope keeps drawing until the finer read lands, rather than a torn mixture.
    private var usableDetail: WaveformPeaks? {
        guard let detail = viewModel.laneDetail[lane], let span = viewModel.laneDetailSpan else { return nil }
        guard span.start <= window.start, span.end >= window.end else { return nil }
        return detail
    }
}

/// Draws a peak envelope over a window of the **recording**.
///
/// Buckets are indexed from `peaksStart`, which is where bucket 0 sits **in source time**.
/// The whole-file cache is bucketed in that lane's own audio-file time, so its bucket 0 is at
/// the lane offset; a detail read is already bucketed from the window's start.
///
/// Typed as a `Stamp<Source>` rather than a bare `TimeInterval` on purpose: the audio-file
/// clock is a fourth clock, and when this parameter was untyped the two call-site branches
/// passed values from *different* clocks into it — one of them sign-flipped.
struct WaveformTrace: View, Equatable {
    let peaks: WaveformPeaks?
    let peaksStart: Stamp<Source>
    let window: StampSpan<Source>
    let isMuted: Bool
    let scale: WaveformScale

    private struct Column {
        let x: Double
        let peakTop: Double
        let peakBottom: Double
        let rmsTop: Double
        let rmsBottom: Double
    }

    var body: some View {
        Canvas { context, size in
            guard let peaks, peaks.bucketCount > 0, window.duration > 0 else { return }

            let midY = size.height / 2
            let columns = self.columns(peaks: peaks, size: size, midY: midY)
            guard !columns.isEmpty else { return }

            // Two filled bands, the way Audacity draws it: a light outer envelope of the
            // extremes, and a solid inner band of RMS. Peaks alone are spiky and say little
            // about where speech actually is; the RMS body is what makes it readable.
            let colour: Color = isMuted ? .secondary : .accentColor
            context.fill(
                band(columns, top: \.peakTop, bottom: \.peakBottom, midY: midY),
                with: .color(colour.opacity(isMuted ? 0.2 : 0.45))
            )
            context.fill(
                band(columns, top: \.rmsTop, bottom: \.rmsBottom, midY: midY),
                with: .color(colour.opacity(isMuted ? 0.35 : 0.95))
            )

            var centre = Path()
            centre.move(to: CGPoint(x: 0, y: midY))
            centre.addLine(to: CGPoint(x: size.width, y: midY))
            context.stroke(centre, with: .color(colour.opacity(0.5)), lineWidth: 0.5)
        }
    }

    private func columns(peaks: WaveformPeaks, size: CGSize, midY: Double) -> [Column] {
        var result: [Column] = []
        result.reserveCapacity(Int(size.width))

        for column in 0..<Int(size.width) {
            // The axis is source time, so this is one subtraction rather than a chain of
            // clock conversions.
            let source = window.start.seconds
                + Double(column) / Double(size.width) * window.duration
            let bucket = Int((source - peaksStart.seconds) * Double(peaks.bucketsPerSecond))
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
    /// Every column gets at least a hairline of height so a quiet-but-present stretch still
    /// draws as a line — the difference between "silent" and "quiet" is what a cut decision
    /// turns on.
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
