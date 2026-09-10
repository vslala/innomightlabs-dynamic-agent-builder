import AVFoundation
import SwiftUI

/// Hosts an `AVPlayerLayer`. SwiftUI has no native player surface that exposes the layer, and
/// `VideoPlayer` would bring its own controls.
struct VideoPreviewView: NSViewRepresentable {
    let player: AVPlayer

    func makeNSView(context: Context) -> PlayerLayerView {
        let view = PlayerLayerView()
        view.player = player
        return view
    }

    func updateNSView(_ view: PlayerLayerView, context: Context) {
        view.player = player
    }
}

final class PlayerLayerView: NSView {
    private let playerLayer = AVPlayerLayer()

    var player: AVPlayer? {
        get { playerLayer.player }
        set { playerLayer.player = newValue }
    }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        // The composition already letterboxes into its render size; the layer just fits that
        // render size into whatever the window gives it.
        playerLayer.videoGravity = .resizeAspect
        playerLayer.backgroundColor = .black
        layer?.addSublayer(playerLayer)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) is not used — this view is only created from SwiftUI")
    }

    override func layout() {
        super.layout()
        playerLayer.frame = bounds
    }
}
