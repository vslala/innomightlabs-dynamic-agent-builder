import SwiftUI

/// The timeline: five named lanes on one shared axis.
///
/// Not a generic NLE. Aura recorded the session, so the lane set is fixed and named — Captions,
/// Screen, Camera, Voice, System Audio — and there is no track-management surface because there
/// are no tracks to manage.
///
/// The axis is the **recording's**, not the edited timeline's, which is what makes a cut
/// visible at all: on the edited timeline the removed material is simply absent. Cuts,
/// selection, splits, markers and the playhead are drawn once, in a single overlay spanning
/// every lane, so they cannot drift out of alignment between rows.
struct TimelineView: View {
    @ObservedObject var viewModel: ReviewViewModel

    /// Set while a drag is building a selection, so a click can be told from a drag.
    @State private var dragOrigin: Stamp<Source>?
    /// Where a marker is being dragged to, so it tracks the cursor before the edit commits.
    @State private var draggingMarker: (id: String, stamp: Stamp<Source>)?
    @State private var lastMagnification: CGFloat = 1
    /// Reveals the overlay scrollbar. Tracked here rather than inside the scrollbar itself, so
    /// hovering anywhere over the lanes brings it up — a control you have to find before it
    /// appears is not much of a control.
    @State private var isHoveringLanes = false

    private let gutterWidth: CGFloat = 152
    private let rulerHeight: CGFloat = 26
    private let laneSpacing: CGFloat = 5

    private var window: StampSpan<Source> { viewModel.visibleSpan }

    private var lanes: [TimelineLane] {
        TimelineLane.allCases.filter { lane in
            if lane == .captions { return viewModel.showsCaptions && !viewModel.projection.cues.isEmpty }
            if let audio = lane.audioLane {
                return viewModel.timeline?.audio.contains { $0.lane == audio } ?? false
            }
            if let video = lane.videoLane {
                return viewModel.probes.contains { $0.kind.videoLane == video }
            }
            return false
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            TimelineToolbar(viewModel: viewModel)

            HStack(alignment: .top, spacing: 0) {
                labelColumn
                    .frame(width: gutterWidth)

                GeometryReader { geometry in
                    let width = geometry.size.width

                    ZStack(alignment: .topLeading) {
                        contentColumn(width: width)
                        overlays(width: width)

                        // Overlaid at the bottom rather than given a row of its own, like the
                        // system's overlay scrollers: it costs no lane height and adds no
                        // permanent furniture.
                        VStack(spacing: 0) {
                            Spacer(minLength: 0)
                            TimelineScrollBar(viewModel: viewModel, isVisible: isHoveringLanes)
                        }
                    }
                    .frame(width: width, alignment: .topLeading)
                    .contentShape(Rectangle())
                    .onHover {
                        isHoveringLanes = $0
                        viewModel.isPointerOverTimeline = $0
                    }
                    .onAppear { viewModel.requestWaveformDetail(viewWidth: width) }
                    .onChange(of: window) { _, _ in viewModel.requestWaveformDetail(viewWidth: width) }
                    .onChange(of: width) { _, new in viewModel.requestWaveformDetail(viewWidth: new) }
                    .gesture(dragGesture(width: width))
                    // Simultaneous so a single click still reaches the drag gesture. Spatial
                    // because restoring a cut needs to know which one was clicked.
                    .simultaneousGesture(
                        SpatialTapGesture(count: 2).onEnded { value in
                            viewModel.restoreCutRegion(at: stamp(atX: value.location.x, width: width))
                        }
                    )
                }
            }
            .padding(.horizontal, AuraTheme.Space.md)
            .padding(.bottom, AuraTheme.Space.md)
        }
        .background(AuraTheme.surface)
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

    // MARK: - Columns
    //
    // The two columns are built from the same row heights so every label lines up with its
    // lane. Any change to one list has to be mirrored in the other.

    private var labelColumn: some View {
        VStack(spacing: laneSpacing) {
            Color.clear.frame(height: rulerHeight)

            ForEach(lanes) { lane in
                LaneLabel(viewModel: viewModel, lane: lane)
                    .frame(height: lane.height)
            }
        }
    }

    private func contentColumn(width: CGFloat) -> some View {
        VStack(spacing: laneSpacing) {
            TimelineTicksView(window: window)
                .frame(height: rulerHeight)

            ForEach(lanes) { lane in
                laneContent(lane, width: width)
                    .frame(height: lane.height)
            }
        }
    }

    @ViewBuilder
    private func laneContent(_ lane: TimelineLane, width: CGFloat) -> some View {
        switch lane {
        case .captions:
            CaptionLaneView(viewModel: viewModel, window: window, height: lane.height)

        case .screen, .camera:
            FilmstripLaneView(
                frames: lane.videoLane.flatMap { viewModel.filmstrips[$0] },
                window: window,
                height: lane.height
            )

        case .voice, .systemAudio:
            if let audio = lane.audioLane {
                AudioLaneWaveform(viewModel: viewModel, lane: audio, height: lane.height)
            }
        }
    }

    // MARK: - Shared overlays

    /// Drawn once across every lane. Per-lane copies would be five chances to disagree about
    /// where a cut is.
    @ViewBuilder
    private func overlays(width: CGFloat) -> some View {
        cutRegions(width: width)
        splits(width: width)
        selection(width: width)
        markers(width: width)
        playhead(width: width)
    }

    private func cutRegions(width: CGFloat) -> some View {
        ForEach(viewModel.projection.regions.filter { $0.isCut && $0.span.overlaps(window) }) { region in
            let start = window.fraction(of: region.span.start) * width
            let end = window.fraction(of: region.span.end) * width
            let selected = viewModel.selectedCutRegionID == region.id

            Rectangle()
                .fill(ReviewPalette.cut.opacity(selected ? 0.34 : 0.2))
                .overlay(alignment: .leading) {
                    Rectangle().fill(ReviewPalette.cut.opacity(0.75)).frame(width: 1)
                }
                .overlay(alignment: .trailing) {
                    Rectangle().fill(ReviewPalette.cut.opacity(0.75)).frame(width: 1)
                }
                // At least a hairline, so a 100ms word cut is still visible when the whole
                // recording is on screen.
                .frame(width: max(2, end - start))
                .offset(x: start)
                // Not interactive: a gesture here is a descendant of the selection drag and
                // would outrank it, which silently kills click-to-select on cut regions.
                .allowsHitTesting(false)
                .help(region.label.map { "Cut: \($0) — double-click to restore" }
                      ?? "Cut — double-click to restore")
        }
    }

    private func splits(width: CGFloat) -> some View {
        ForEach(viewModel.projection.splits.filter { window.contains($0) }, id: \.seconds) { split in
            Rectangle()
                .fill(ReviewPalette.split)
                .frame(width: 1)
                .offset(x: window.fraction(of: split) * width)
                .allowsHitTesting(false)
        }
    }

    @ViewBuilder
    private func selection(width: CGFloat) -> some View {
        if let selection = viewModel.selection, selection.overlaps(window) {
            let start = window.fraction(of: selection.start) * width
            let end = window.fraction(of: selection.end) * width

            Rectangle()
                .fill(ReviewPalette.selection.opacity(0.18))
                .overlay {
                    Rectangle().stroke(ReviewPalette.selection.opacity(0.85), lineWidth: 1)
                }
                .frame(width: max(1, end - start))
                .offset(x: start)
                .allowsHitTesting(false)
        }
    }

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

    @ViewBuilder
    private func playhead(width: CGFloat) -> some View {
        if let source = viewModel.projection.sourceTime(forComposition: Stamp(viewModel.playhead)),
           window.contains(source) {
            Rectangle()
                .fill(AuraTheme.accent)
                .frame(width: 1.5)
                .overlay(alignment: .top) {
                    Circle()
                        .fill(AuraTheme.accent)
                        .frame(width: 7, height: 7)
                        .offset(y: -3)
                }
                .offset(x: window.fraction(of: source) * width)
                .allowsHitTesting(false)
        }
    }

    // MARK: - Gestures

    /// A drag builds a selection; a click without movement seeks, selects a cut region, or —
    /// when the blade is armed — splits.
    private func dragGesture(width: CGFloat) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { value in
                let origin = dragOrigin ?? stamp(atX: value.startLocation.x, width: width)
                dragOrigin = origin
                // Suspends playhead following for the duration of the gesture, so the view
                // cannot page out from under the cursor mid-drag.
                viewModel.isDraggingTimeline = true
                if abs(value.translation.width) > 3 {
                    viewModel.select(from: origin, to: stamp(atX: value.location.x, width: width))
                }
            }
            .onEnded { value in
                defer {
                    dragOrigin = nil
                    viewModel.isDraggingTimeline = false
                }
                let stamp = self.stamp(atX: value.location.x, width: width)

                guard abs(value.translation.width) <= 3 else {
                    viewModel.select(from: dragOrigin ?? stamp, to: stamp)
                    return
                }
                if viewModel.isBladeArmed {
                    viewModel.splitAt(stamp)
                } else {
                    viewModel.handleLaneClick(at: stamp)
                }
            }
    }

    /// Only editorial markers move. A recording marker is a fact from `events.jsonl`, so
    /// dragging one would be falsifying the record rather than editing.
    ///
    /// Uses `translation`, not `location`: the gesture is attached to the 9pt glyph, so
    /// `DragGesture`'s default `.local` space measures from that view's origin.
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

    private func dragged(_ marker: ProjectedMarker, by dx: CGFloat, width: CGFloat) -> Stamp<Source> {
        let seconds = marker.source.seconds + Double(dx / width) * window.duration
        return Stamp(min(max(0, seconds), viewModel.recordingDuration))
    }

    private func stamp(atX x: CGFloat, width: CGFloat) -> Stamp<Source> {
        guard width > 0 else { return window.start }
        return window.stamp(atFraction: Double(x / width))
    }
}

// MARK: - Lane label

/// The gutter cell for one lane. Per-lane controls live in a context menu rather than inline,
/// so five lanes do not add up to a wall of sliders.
private struct LaneLabel: View {
    @ObservedObject var viewModel: ReviewViewModel
    let lane: TimelineLane

    private var isMuted: Bool {
        guard let audio = lane.audioLane else { return false }
        return viewModel.store?.document.settings(for: audio).muted ?? false
    }

    var body: some View {
        HStack(spacing: AuraTheme.Space.sm) {
            Image(systemName: isMuted ? "speaker.slash" : lane.symbol)
                .font(.system(size: 11))
                .foregroundStyle(isMuted ? ReviewPalette.cut : AuraTheme.textSecondary)
                .frame(width: 16)

            Text(lane.title)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(isMuted ? AuraTheme.textTertiary : AuraTheme.textSecondary)
                .lineLimit(1)

            Spacer(minLength: 0)
        }
        .padding(.trailing, AuraTheme.Space.sm)
        .frame(maxHeight: .infinity)
        .contentShape(Rectangle())
        .contextMenu { menu }
    }

    @ViewBuilder
    private var menu: some View {
        if let audio = lane.audioLane {
            Button(isMuted ? "Unmute" : "Mute") { viewModel.setLaneMuted(audio, !isMuted) }
            Divider()
            Menu("Level") {
                ForEach([0.0, 0.25, 0.5, 0.75, 1.0], id: \.self) { gain in
                    Button(String(format: "%.0f%%", gain * 100)) {
                        viewModel.setLaneGain(audio, gain)
                    }
                }
            }
            Menu("Sync") {
                Button("10ms earlier") { viewModel.nudgeLaneOffset(audio, by: -0.01) }
                Button("10ms later") { viewModel.nudgeLaneOffset(audio, by: 0.01) }
                if viewModel.laneOffset(audio) != 0 {
                    Divider()
                    Button("Reset (\(String(format: "%+.0fms", viewModel.laneOffset(audio) * 1000)))") {
                        viewModel.resetLaneOffset(audio)
                    }
                }
            }
        } else if lane == .captions {
            Button("Hide captions") { viewModel.showsCaptions = false }
        } else {
            Text("Recorded by Aura — nothing to configure")
        }
    }
}

// MARK: - Ticks

/// Time labels along the top of the lane stack, on the source axis like everything below.
private struct TimelineTicksView: View {
    let window: StampSpan<Source>

    var body: some View {
        GeometryReader { geometry in
            let width = geometry.size.width
            let step = Self.tickStep(forVisible: window.duration, width: width)

            ZStack(alignment: .topLeading) {
                ForEach(ticks(step: step), id: \.self) { seconds in
                    let x = window.fraction(of: Stamp<Source>(seconds)) * width

                    VStack(spacing: 2) {
                        Text(TimeFormatting.timecode(seconds))
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(AuraTheme.textTertiary)
                        Rectangle()
                            .fill(AuraTheme.border)
                            .frame(width: 1, height: 5)
                    }
                    .fixedSize()
                    .offset(x: x - 18)
                }
            }
        }
    }

    private func ticks(step: TimeInterval) -> [TimeInterval] {
        guard step > 0, window.duration > 0 else { return [] }
        let first = (window.start.seconds / step).rounded(.up) * step
        var result: [TimeInterval] = []
        var value = first
        // Bounded so a pathological step cannot spin: the view is only ever a few hundred
        // points wide.
        while value <= window.end.seconds, result.count < 64 {
            result.append(value)
            value += step
        }
        return result
    }

    /// Picks a round interval that leaves at least ~76pt between labels, so timecodes never
    /// overlap regardless of zoom.
    static func tickStep(forVisible duration: TimeInterval, width: CGFloat) -> TimeInterval {
        guard duration > 0, width > 0 else { return 1 }
        let candidates: [TimeInterval] = [
            0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600
        ]
        let minimumSpacing: CGFloat = 76
        let maximumTicks = Double(max(1, width / minimumSpacing))
        return candidates.first { duration / $0 <= maximumTicks } ?? candidates.last!
    }
}
