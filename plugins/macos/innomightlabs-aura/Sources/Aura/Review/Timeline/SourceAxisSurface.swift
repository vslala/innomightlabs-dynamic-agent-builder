import SwiftUI

/// A surface on the recording's source-time axis: draws cuts, the selection and the playhead
/// over its content, and owns the click/drag semantics — a drag builds a selection, a click
/// seeks or splits, a double-click on a cut restores it.
///
/// Used today only by `AudioStageView`. `TimelineView` has the equivalent logic inline rather
/// than sharing this: there, editorial markers must remain a *descendant* of the exact view
/// carrying `.gesture(dragGesture)` for `.highPriorityGesture(markerDrag)` to correctly outrank
/// it, and restructuring that relationship through a generic wrapper is not something that can
/// be verified without interactively testing the running app. Consolidating the two once that
/// is confirmed manually removes this duplication; until then, the two are logically identical
/// on purpose — a change to selection, cut-restore or split behavior here should be mirrored
/// in `TimelineView`, and vice versa.
///
/// Markers are deliberately not drawn here — they are draggable and need a host's gesture
/// state, and only the timeline offers them.
struct SourceAxisSurface<Content: View>: View {
    @ObservedObject var viewModel: ReviewViewModel
    let window: StampSpan<Source>
    @ViewBuilder var content: (CGFloat) -> Content

    /// Set while a drag is building a selection, so a click can be told from a drag.
    @State private var dragOrigin: Stamp<Source>?

    var body: some View {
        GeometryReader { geometry in
            let width = geometry.size.width

            ZStack(alignment: .topLeading) {
                content(width)
                cutRegions(width: width)
                splits(width: width)
                selection(width: width)
                playhead(width: width)
            }
            .frame(width: width, alignment: .topLeading)
            .contentShape(Rectangle())
            .gesture(dragGesture(width: width))
            // Simultaneous so a single click still reaches the drag gesture. Spatial because
            // restoring a cut needs to know which one was clicked.
            .simultaneousGesture(
                SpatialTapGesture(count: 2).onEnded { value in
                    viewModel.restoreCutRegion(at: stamp(atX: value.location.x, width: width))
                }
            )
        }
    }

    // MARK: - Overlays

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

    private func stamp(atX x: CGFloat, width: CGFloat) -> Stamp<Source> {
        guard width > 0 else { return window.start }
        return window.stamp(atFraction: Double(x / width))
    }
}
