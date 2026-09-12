import Foundation

/// How the screen and camera are arranged in the frame.
///
/// Every mode is expressible as a camera-overlay keyframe, so switching modes touches no
/// compositor code — it is an ordinary, undoable edit like moving the camera by hand. And
/// because it is a keyframe, a mode change applies from the playhead onwards rather than
/// retroactively across the whole recording.
///
/// Side-by-side is deliberately absent: it needs the *screen* transformed as well, which the
/// single-overlay model cannot express.
enum LayoutMode: String, CaseIterable, Identifiable, Sendable {
    case screenOnly
    case screenAndCamera
    case cameraOnly

    var id: String { rawValue }

    var title: String {
        switch self {
        case .screenOnly: return "Screen only"
        case .screenAndCamera: return "Screen + camera"
        case .cameraOnly: return "Camera only"
        }
    }

    var symbol: String {
        switch self {
        case .screenOnly: return "rectangle"
        case .screenAndCamera: return "rectangle.inset.bottomleading.filled"
        case .cameraOnly: return "person.crop.rectangle"
        }
    }

    /// The overlay this mode implies.
    ///
    /// `cameraOnly` fills the frame, which covers the screen entirely — the Core Image path
    /// fills its rect rather than aspect-fitting, so there is no letterbox gap to see around.
    func keyframe(at time: TimeInterval, defaultRect: NormalizedRect) -> OverlayKeyframe {
        switch self {
        case .screenOnly:
            return OverlayKeyframe(t: time, rect: defaultRect, visible: false)
        case .screenAndCamera:
            return OverlayKeyframe(t: time, rect: defaultRect, visible: true)
        case .cameraOnly:
            return OverlayKeyframe(
                t: time,
                rect: NormalizedRect(x: 0, y: 0, width: 1, height: 1),
                visible: true
            )
        }
    }

    /// Classifies an existing keyframe, so the UI can show which mode is current.
    static func mode(of keyframe: OverlayKeyframe?) -> LayoutMode {
        guard let keyframe else { return .screenOnly }
        guard keyframe.visible else { return .screenOnly }
        let rect = keyframe.rect
        let fillsFrame = rect.width > 0.98 && rect.height > 0.98
            && rect.x < 0.02 && rect.y < 0.02
        return fillsFrame ? .cameraOnly : .screenAndCamera
    }
}
