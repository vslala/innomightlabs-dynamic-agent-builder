import AVFoundation
import SwiftUI

/// The review window: composited preview with the camera overlay on top, transport and
/// timeline below, transcript alongside.
struct ReviewWindowView: View {
    @ObservedObject var viewModel: ReviewViewModel

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
                    .frame(height: 140)
            }
            .frame(minWidth: 560)

            TranscriptPanelView(viewModel: viewModel)
                .frame(minWidth: 260, idealWidth: 320)
        }
        .overlay(alignment: .top) { errorBanner }
    }

    private var preview: some View {
        VideoPreviewView(player: viewModel.player)
            .background(.black)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .overlay { overlayHandles }
            .onTapGesture { viewModel.togglePlayback() }
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
                .keyboardShortcut(.space, modifiers: [])

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
                }

                if let store = viewModel.store {
                    Button {
                        store.undo()
                    } label: {
                        Image(systemName: "arrow.uturn.backward")
                    }
                    .disabled(!store.canUndo)
                    .keyboardShortcut("z", modifiers: .command)

                    Button {
                        store.redo()
                    } label: {
                        Image(systemName: "arrow.uturn.forward")
                    }
                    .disabled(!store.canRedo)
                    .keyboardShortcut("z", modifiers: [.command, .shift])
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
            HStack {
                Text(message)
                    .font(.caption)
                Spacer()
                Button("Dismiss") { viewModel.lastError = nil }
                    .font(.caption)
            }
            .padding(8)
            .background(.red.opacity(0.85))
            .foregroundStyle(.white)
        }
    }
}
