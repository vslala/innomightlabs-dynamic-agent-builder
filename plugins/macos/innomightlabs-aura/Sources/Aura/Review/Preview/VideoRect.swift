import CoreGraphics

/// Where the picture actually sits inside a container.
///
/// `AVPlayerLayer` uses `resizeAspect`, so a 16:9 composition in a 4:3 container is letterboxed
/// and the picture occupies only part of the view. Anything drawn on top — subtitles, camera
/// handles — has to be positioned against *this* rect, not the container's bounds, or it drifts
/// off the image as the window's aspect changes.
enum VideoRect {
    static func fitted(renderSize: CGSize, in container: CGSize) -> CGRect {
        guard renderSize.width > 0, renderSize.height > 0,
              container.width > 0, container.height > 0
        else { return CGRect(origin: .zero, size: container) }

        let scale = min(container.width / renderSize.width, container.height / renderSize.height)
        let size = CGSize(width: renderSize.width * scale, height: renderSize.height * scale)
        return CGRect(
            x: (container.width - size.width) / 2,
            y: (container.height - size.height) / 2,
            width: size.width,
            height: size.height
        )
    }
}
