import SwiftUI

/// The preview: the picture, the camera handles, and the subtitles.
///
/// All three overlays are positioned against the fitted video rect rather than this view's
/// bounds, because the player letterboxes.
struct PreviewStageView: View {
    @ObservedObject var viewModel: ReviewViewModel

    @State private var isHovering = false

    var body: some View {
        GeometryReader { geometry in
            let container = geometry.size
            let video = VideoRect.fitted(renderSize: renderSize, in: container)

            ZStack {
                VideoPreviewView(player: viewModel.player)

                cameraHandles(videoRect: video)

                if let subtitle = viewModel.activeSubtitle {
                    SubtitleOverlayView(text: subtitle, videoRect: video)
                }
            }
            .frame(width: container.width, height: container.height)
            .background(Color.black)
            .contentShape(Rectangle())
            .onTapGesture { viewModel.togglePlayback() }
            .onHover { isHovering = $0 }
        }
    }

    private var renderSize: CGSize {
        viewModel.timeline?.renderSize ?? CGSize(width: 16, height: 9)
    }

    @ViewBuilder
    private func cameraHandles(videoRect: CGRect) -> some View {
        if let timeline = viewModel.timeline,
           let camera = timeline.overlay,
           let size = camera.probe.displaySize,
           let keyframe = viewModel.currentOverlay,
           keyframe.visible {
            CameraOverlayView(
                renderSize: timeline.renderSize,
                cameraDisplaySize: size,
                keyframe: keyframe,
                style: viewModel.cameraStyle,
                showsHandles: isHovering,
                onCommit: { viewModel.setOverlay(rect: $0, visible: keyframe.visible) }
            )
            .frame(width: videoRect.width, height: videoRect.height)
            .position(x: videoRect.midX, y: videoRect.midY)
        }
    }
}
