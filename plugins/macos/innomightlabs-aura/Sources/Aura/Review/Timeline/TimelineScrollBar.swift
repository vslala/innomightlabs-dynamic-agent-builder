import SwiftUI

/// A slim horizontal scrollbar for panning the timeline.
///
/// Overlaid on the lanes rather than given its own row, in the manner of the system's overlay
/// scrollers: it appears only while the pointer is over the timeline, so it costs no height and
/// adds no permanent furniture to a surface the design wants quiet.
///
/// Absent entirely when the whole recording already fits, since there is then nothing to
/// scroll and a full-width thumb would only be something to try to drag.
struct TimelineScrollBar: View {
    @ObservedObject var viewModel: ReviewViewModel
    let isVisible: Bool

    /// Where the thumb was when the drag began, so the mapping is against a fixed origin
    /// rather than accumulating rounding from each delta.
    @State private var dragOrigin: CGFloat?
    @State private var isHoveringThumb = false

    private var height: CGFloat { isHoveringThumb || dragOrigin != nil ? 9 : 6 }

    var body: some View {
        GeometryReader { geometry in
            let trackWidth = geometry.size.width

            if let visibleDuration = viewModel.visibleDuration,
               let thumb = ScrollBarGeometry.thumb(
                   viewportStart: viewModel.viewportStart,
                   visibleDuration: visibleDuration,
                   recordingDuration: viewModel.recordingDuration,
                   trackWidth: trackWidth
               ) {
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(AuraTheme.background.opacity(0.55))
                        .frame(height: height)

                    Capsule()
                        .fill(AuraTheme.textSecondary.opacity(isHoveringThumb ? 0.55 : 0.32))
                        .frame(width: thumb.width, height: height)
                        .offset(x: thumb.x)
                        .onHover { isHoveringThumb = $0 }
                        .gesture(drag(thumb: thumb, trackWidth: trackWidth, visible: visibleDuration))
                }
                .frame(height: 14, alignment: .center)
                .opacity(isVisible ? 1 : 0)
                // Kept out of the hit path while hidden, so an invisible thumb cannot swallow
                // a click meant for the waveform underneath.
                .allowsHitTesting(isVisible)
                .animation(.easeOut(duration: 0.14), value: isVisible)
                .animation(.easeOut(duration: 0.1), value: height)
            }
        }
        .frame(height: 14)
    }

    private func drag(
        thumb: ScrollBarGeometry.Thumb,
        trackWidth: CGFloat,
        visible: TimeInterval
    ) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { value in
                let origin = dragOrigin ?? thumb.x
                dragOrigin = origin
                // Suspends playhead following, so the view cannot page while being dragged.
                viewModel.isDraggingTimeline = true
                apply(x: origin + value.translation.width, thumb: thumb, trackWidth: trackWidth, visible: visible)
            }
            .onEnded { value in
                let origin = dragOrigin ?? thumb.x
                apply(x: origin + value.translation.width, thumb: thumb, trackWidth: trackWidth, visible: visible)
                dragOrigin = nil
                viewModel.isDraggingTimeline = false
            }
    }

    private func apply(
        x: CGFloat,
        thumb: ScrollBarGeometry.Thumb,
        trackWidth: CGFloat,
        visible: TimeInterval
    ) {
        viewModel.scrollViewport(to: ScrollBarGeometry.viewportStart(
            thumbX: x,
            thumbWidth: thumb.width,
            visibleDuration: visible,
            recordingDuration: viewModel.recordingDuration,
            trackWidth: trackWidth
        ))
    }
}
