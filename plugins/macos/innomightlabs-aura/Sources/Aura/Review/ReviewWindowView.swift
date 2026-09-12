import AVFoundation
import SwiftUI

/// The review window: composited preview with the camera overlay on top, transport and
/// timeline below, transcript alongside.
struct ReviewWindowView: View {
    @ObservedObject var viewModel: ReviewViewModel

    @State private var isHoveringPreview = false

    var body: some View {
        Group {
            switch viewModel.state {
            case .loading:
                VStack(spacing: 8) {
                    ProgressView()
                    Text("Opening \(viewModel.folder.id)…")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            case .failed(let message):
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.largeTitle)
                        .foregroundStyle(.secondary)
                    Text(message)
                        .font(.callout)
                        .multilineTextAlignment(.center)
                }
                .padding(40)
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            case .ready:
                content
            }
        }
        .frame(minWidth: 900, minHeight: 600)
        .task { await viewModel.load() }
    }

    private var content: some View {
        HSplitView {
            VStack(spacing: 0) {
                preview
                Divider()
                transport
                Divider()
                WaveformLanesView(viewModel: viewModel)
                    .frame(height: 196)
            }
            .frame(minWidth: 560)

            VStack(spacing: 0) {
                TranscriptPanelView(viewModel: viewModel)
                Divider()
                AgentEditPanelView(viewModel: viewModel)
            }
            .frame(minWidth: 300, idealWidth: 360)
        }
        .overlay(alignment: .top) { errorBanner }
    }

    private var preview: some View {
        VideoPreviewView(player: viewModel.player)
            .background(.black)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .overlay { overlayHandles }
            .onTapGesture { viewModel.togglePlayback() }
            .onHover { isHoveringPreview = $0 }
    }

    @ViewBuilder
    private var overlayHandles: some View {
        if let timeline = viewModel.timeline,
           let camera = timeline.overlay,
           let size = camera.probe.displaySize,
           let keyframe = viewModel.currentOverlay {
            CameraOverlayView(
                renderSize: timeline.renderSize,
                cameraDisplaySize: size,
                keyframe: keyframe,
                style: viewModel.cameraStyle,
                showsHandles: isHoveringPreview,
                onCommit: { viewModel.setOverlay(rect: $0, visible: keyframe.visible) }
            )
        }
    }

    private var transport: some View {
        VStack(spacing: 6) {
            TimelineRulerView(viewModel: viewModel)
                .frame(height: 28)

            HStack(spacing: 12) {
                Button {
                    viewModel.togglePlayback()
                } label: {
                    Image(systemName: viewModel.isPlaying ? "pause.fill" : "play.fill")
                }
                // No `.keyboardShortcut` here: an unmodified window-wide shortcut is resolved
                // ahead of the field editor, so it could swallow spaces typed into the agent
                // prompt. `ReviewKeyCommand` owns the keyboard and checks focus first.

                Text("\(TimeFormatting.timecode(Timeline.seconds(viewModel.playhead))) / \(TimeFormatting.timecode(Timeline.seconds(viewModel.duration)))")
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)

                Spacer()

                if viewModel.timeline?.overlay != nil, let keyframe = viewModel.currentOverlay {
                    Button {
                        viewModel.toggleOverlayVisibility()
                    } label: {
                        Label(
                            keyframe.visible ? "Hide Camera" : "Show Camera",
                            systemImage: keyframe.visible ? "video.slash" : "video"
                        )
                    }
                    .help("Takes effect from the playhead onwards")

                    CameraStyleMenu(viewModel: viewModel)
                }

                if let store = viewModel.store {
                    Button {
                        store.undo()
                    } label: {
                        Image(systemName: "arrow.uturn.backward")
                    }
                    .disabled(!store.canUndo)

                    Button {
                        store.redo()
                    } label: {
                        Image(systemName: "arrow.uturn.forward")
                    }
                    .disabled(!store.canRedo)
                }

                ExportButton(viewModel: viewModel)
            }
            .padding(.horizontal, 12)
        }
        .padding(.vertical, 8)
    }

    @ViewBuilder
    private var errorBanner: some View {
        if let message = viewModel.lastError {
            banner(message, background: .red.opacity(0.85), foreground: .white) {
                viewModel.lastError = nil
            }
        }

        // Distinct from the error banner on purpose: this reports something expected, and
        // colouring it red would make a benign event look like a failure.
        if let notice = viewModel.lastNotice {
            banner(notice, background: .thinMaterial, foreground: .primary) {
                viewModel.lastNotice = nil
            }
        }
    }

    private func banner(
        _ message: String,
        background: some ShapeStyle,
        foreground: some ShapeStyle,
        dismiss: @escaping () -> Void
    ) -> some View {
        HStack {
            Text(message)
                .font(.caption)
                .fixedSize(horizontal: false, vertical: true)
            Spacer()
            Button("Dismiss", action: dismiss)
                .font(.caption)
        }
        .padding(8)
        .background(background)
        .foregroundStyle(foreground)
    }
}
