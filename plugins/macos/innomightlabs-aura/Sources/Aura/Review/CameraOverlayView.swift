import SwiftUI

/// Drag and resize handles for the camera picture-in-picture, drawn over the video preview.
///
/// The drag is local `@State` and only commits an `EditOperation` on release: every commit
/// rebuilds the composition and swaps the player item, which is far too expensive to do per
/// mouse-moved event.
///
/// Both the displayed box and the committed rect are aspect-locked to the camera's own ratio,
/// by running them through the same fit the compositor uses. That is what lets the compositor
/// stay on pure scale-and-translate: a rect that always matches the source aspect never needs
/// a crop, so aspect-fit and aspect-fill are indistinguishable and the ambiguous crop-origin
/// question never arises.
struct CameraOverlayView: View {
    let renderSize: CGSize
    let cameraDisplaySize: CGSize
    let keyframe: OverlayKeyframe
    let style: PiPStyle
    /// Handles are chrome, not content: they clutter the frame when the pointer is elsewhere,
    /// so they appear on hover and stay while a drag is in flight.
    let showsHandles: Bool
    let onCommit: (NormalizedRect) -> Void

    @State private var dragOffset: CGSize = .zero
    @State private var resizeScale: CGFloat = 1
    @State private var isInteracting = false

    private static let minNormalizedWidth: Double = 0.05

    var body: some View {
        GeometryReader { geometry in
            // Where the video actually sits inside the view, since the layer letterboxes.
            let videoRect = PiPGeometry.fittedRect(
                displaySize: renderSize,
                destination: CGRect(origin: .zero, size: geometry.size)
            )
            let live = liveRect(in: videoRect)

            if keyframe.visible {
                let active = showsHandles || isInteracting

                Rectangle()
                    .stroke(.white.opacity(active ? 0.9 : 0), lineWidth: 1.5)
                    .background(Color.white.opacity(0.001)) // hit area without tinting the video
                    .frame(width: live.width, height: live.height)
                    .overlay(alignment: .bottomTrailing) {
                        if active { resizeHandle(videoRect: videoRect, live: live) }
                    }
                    .position(x: live.midX, y: live.midY)
                    .gesture(moveGesture(videoRect: videoRect))
                    .animation(.easeOut(duration: 0.12), value: active)
            }
        }
    }

    private func resizeHandle(videoRect: CGRect, live: CGRect) -> some View {
        Circle()
            .fill(.white)
            .frame(width: 10, height: 10)
            .offset(x: 5, y: 5)
            .gesture(resizeGesture(videoRect: videoRect, live: live))
    }

    /// The rect as currently shown, including any in-flight gesture.
    ///
    /// Run through the same fit the compositor applies, rather than deriving an aspect here.
    /// That is what guarantees the handles frame the video the user can actually see — a
    /// stored rect whose aspect doesn't match the camera's (the default corner rect, for one)
    /// gets letterboxed by the compositor, and handles drawn around the stored rect would sit
    /// outside the picture. Committing the fitted rect back makes it self-correcting.
    private func liveRect(in videoRect: CGRect) -> CGRect {
        let base = keyframe.rect
        let destination = CGRect(
            x: videoRect.minX + base.x * videoRect.width + dragOffset.width,
            y: videoRect.minY + base.y * videoRect.height + dragOffset.height,
            width: base.width * resizeScale * videoRect.width,
            height: base.height * resizeScale * videoRect.height
        )
        // Core Image fills the rect, so the handles frame the rect itself rather than a
        // letterboxed subrect. A circle is squared from the rect's origin, matching the render.
        return PiPMask.drawnRect(for: style, in: destination)
    }

    private func moveGesture(videoRect: CGRect) -> some Gesture {
        DragGesture()
            .onChanged {
                isInteracting = true
                dragOffset = $0.translation
            }
            .onEnded { _ in
                commit(liveRect(in: videoRect), in: videoRect)
                dragOffset = .zero
                isInteracting = false
            }
    }

    private func resizeGesture(videoRect: CGRect, live: CGRect) -> some Gesture {
        DragGesture()
            .onChanged { value in
                guard live.width > 0 else { return }
                isInteracting = true
                let proposed = (live.width + value.translation.width) / live.width
                resizeScale = max(0.1, min(6, proposed))
            }
            .onEnded { _ in
                commit(liveRect(in: videoRect), in: videoRect)
                resizeScale = 1
                isInteracting = false
            }
    }

    /// Converts back to a normalized rect, clamped so the overlay always stays at least
    /// partly on screen and never collapses to nothing.
    private func commit(_ rect: CGRect, in videoRect: CGRect) {
        guard videoRect.width > 0, videoRect.height > 0 else { return }

        let width = min(1, max(Self.minNormalizedWidth, rect.width / videoRect.width))
        let height = min(1, max(Self.minNormalizedWidth, rect.height / videoRect.height))
        let x = min(1 - width, max(0, (rect.minX - videoRect.minX) / videoRect.width))
        let y = min(1 - height, max(0, (rect.minY - videoRect.minY) / videoRect.height))

        onCommit(NormalizedRect(x: x, y: y, width: width, height: height))
    }
}
