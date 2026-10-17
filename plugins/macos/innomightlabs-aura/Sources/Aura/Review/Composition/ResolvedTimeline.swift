import CoreMedia
import Foundation

/// How the camera picture-in-picture is drawn.
///
/// The built-in compositor supports only an affine transform, opacity, and an axis-aligned
/// crop, so anything here beyond a plain rectangle requires `CoreImagePiPCompositor`. The
/// style lives in the edit document, so `LayerInstructionCompositionBuilder` remains valid
/// for the plain case and the expensive compositor is used only when it is actually needed.
struct PiPStyle: Codable, Hashable, Sendable {
    enum Shape: String, Codable, Sendable, CaseIterable {
        case rectangle
        case rounded
        case circle
    }

    var shape: Shape
    /// Fraction of the overlay's shorter side. Only used by `.rounded`.
    var cornerRadius: Double
    /// Fraction of the overlay's shorter side.
    var borderWidth: Double
    /// sRGB components, 0-1.
    var borderColor: [Double]
    var shadowOpacity: Double
    /// Fraction of the overlay's shorter side.
    var shadowRadius: Double

    static let plain = PiPStyle(
        shape: .rectangle,
        cornerRadius: 0,
        borderWidth: 0,
        borderColor: [1, 1, 1],
        shadowOpacity: 0,
        shadowRadius: 0
    )

    /// Fractions must stay in range or the Core Image filters produce nothing visible.
    var isValid: Bool {
        [cornerRadius, borderWidth, shadowOpacity, shadowRadius].allSatisfy { $0.isFinite && $0 >= 0 && $0 <= 1 }
            && borderColor.count >= 3
            && borderColor.allSatisfy { $0.isFinite && $0 >= 0 && $0 <= 1 }
    }

    /// True when the built-in compositor can render this, which is the cheaper path.
    var isPlainRectangle: Bool {
        shape == .rectangle && borderWidth <= 0 && shadowOpacity <= 0
    }

    private enum CodingKeys: String, CodingKey {
        case shape, cornerRadius, borderWidth, borderColor, shadowOpacity, shadowRadius
    }

    init(
        shape: Shape,
        cornerRadius: Double,
        borderWidth: Double,
        borderColor: [Double],
        shadowOpacity: Double,
        shadowRadius: Double
    ) {
        self.shape = shape
        self.cornerRadius = cornerRadius
        self.borderWidth = borderWidth
        self.borderColor = borderColor
        self.shadowOpacity = shadowOpacity
        self.shadowRadius = shadowRadius
    }

    /// Tolerant, so a document written before any of this existed still loads.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        shape = try container.decodeIfPresent(Shape.self, forKey: .shape) ?? .rectangle
        cornerRadius = try container.decodeIfPresent(Double.self, forKey: .cornerRadius) ?? 0
        borderWidth = try container.decodeIfPresent(Double.self, forKey: .borderWidth) ?? 0
        borderColor = try container.decodeIfPresent([Double].self, forKey: .borderColor) ?? [1, 1, 1]
        shadowOpacity = try container.decodeIfPresent(Double.self, forKey: .shadowOpacity) ?? 0
        shadowRadius = try container.decodeIfPresent(Double.self, forKey: .shadowRadius) ?? 0
    }
}

/// A step keyframe on the **composition** timeline. Holds until the next one.
struct ResolvedOverlayKeyframe: Equatable, Sendable {
    let at: CMTime
    let rect: NormalizedRect
    let visible: Bool
}

struct ResolvedGainKeyframe: Equatable, Sendable {
    let at: CMTime
    let gain: Double
}

/// One recorded file, plus where its content belongs on the session timeline.
struct PlacedSegment: Equatable, Sendable {
    let probe: SourceTrackProbe
    /// How much later this file's content plays than its own timeline implies. See
    /// `SourceTrackProbe.alignmentCorrection`.
    let timeOffset: CMTime
}

struct ResolvedVideoLayer: Equatable, Sendable {
    /// One entry per recorded on-window ("segment") of this kind, ascending. A session that
    /// never switched profiles has exactly one. Every entry is the same device at the same
    /// preset — changing devices or the screen target mid-session is out of scope — so
    /// geometry and colour tags are read from the first, via `probe` below.
    let segments: [PlacedSegment]
    /// Non-empty, sorted, deduplicated, and guaranteed to start at composition time zero.
    let keyframes: [ResolvedOverlayKeyframe]

    var probe: SourceTrackProbe? { segments.first?.probe }
    var timeOffset: CMTime { segments.first?.timeOffset ?? .zero }
}

struct ResolvedAudioLane: Equatable, Sendable {
    let lane: AudioLane
    /// One entry per recorded on-window of this lane, ascending. See `ResolvedVideoLayer.segments`.
    let segments: [PlacedSegment]
    /// Non-empty, sorted, deduplicated, and guaranteed to start at composition time zero.
    let keyframes: [ResolvedGainKeyframe]

    /// The first segment's offset — what a consumer that reasons about "this lane" as a
    /// single thing (the transcript, which is produced from only the microphone's first
    /// on-window) should align against. `ReviewProjector` is the only reader.
    var timeOffset: CMTime { segments.first?.timeOffset ?? .zero }

    var probe: SourceTrackProbe? { segments.first?.probe }
}

/// A re-spoken selection whose clip is on disk and ready to play.
struct ResolvedSpeechReplacement: Equatable, Sendable {
    let id: UUID
    let url: URL
    /// The session time the clip replaces. The clip's own time zero sits at `span.start`.
    let span: TimeSpan
    /// The clip's length. Beyond the span's length the clip plays through a hold in the picture.
    let duration: CMTime
}

/// A line of narration whose clip is on disk and ready to play.
struct ResolvedNarration: Equatable, Sendable {
    let id: UUID
    let url: URL
    /// Session time the clip starts. The clip's own time zero sits here.
    let at: TimeInterval
    let duration: CMTime
}

/// What the compositor draws over the screen: the magnified region and the rendered cursor.
///
/// Carries the `TimeMap` because the compositor is handed composition time, while zooms and the
/// recorded pointer path are in session time.
struct ResolvedDemoEffects: Equatable, Sendable {
    var zooms: [ZoomSegment]
    /// Nil when the session has no recorded pointer, or the user hid the cursor.
    var cursor: CursorPath?
    var cursorStyle: CursorStyle
    let timeMap: TimeMap

    var isEmpty: Bool { zooms.isEmpty && cursor == nil }
}

/// Everything needed to build a composition, as Sendable value types with no AVFoundation
/// objects and — crucially — no way left to be invalid.
///
/// The AVFoundation APIs downstream raise **uncatchable ObjC exceptions** for a non-numeric
/// `CMTime`, a zero `renderSize` or `frameDuration`, overlapping ramps, or a layer
/// instruction naming a track that was never populated. Those are process kills, not Swift
/// errors, so they cannot be caught and recovered from. Concentrating every one of those
/// invariants here — where it is pure and unit-testable — leaves the builder a mechanical
/// transcription with nothing left to get wrong.
struct ResolvedTimeline: Equatable, Sendable {
    let timeMap: TimeMap
    /// Always positive and even in both dimensions.
    let renderSize: CGSize
    /// Always positive.
    let frameDuration: CMTime
    /// The full-frame layer. Nil only when the session has no usable video at all.
    let base: ResolvedVideoLayer?
    /// The picture-in-picture layer, if there is a second video track to put on top.
    let overlay: ResolvedVideoLayer?
    let audio: [ResolvedAudioLane]
    let style: PiPStyle
    /// Source-frame coordinates, only when the base is a screen track.
    var screenCrop: NormalizedRect? = nil
    /// Replacement speech that can actually be played. A replacement whose clip is missing is
    /// absent here, so the original voice keeps playing rather than going silent.
    var speech: [ResolvedSpeechReplacement] = []
    /// The voice lane's own level and mute, **without** the silences cut under each
    /// replacement, so the new speech obeys the same controls the old voice did.
    var speechKeyframes: [ResolvedGainKeyframe] = []
    /// Nil when there is nothing to draw, so the cheap path stays available.
    var effects: ResolvedDemoEffects? = nil
    var narration: [ResolvedNarration] = []

    var duration: CMTime { timeMap.cmDuration }
    var hasVideo: Bool { base != nil }

    /// Whether the built-in compositor can render this faithfully.
    ///
    /// It can only place a layer with an affine transform, which means aspect-**fitting** the
    /// camera into its rect and letterboxing the remainder. That is invisible while the rect
    /// matches the camera's aspect ratio — which the drag handles guarantee — but an agent
    /// can set any rect it likes, and then a camera placed at x = 0 sits inset from the edge
    /// with a visible gap beside it. Core Image fills the rect instead, so a mismatched rect
    /// routes there rather than being drawn wrongly by the cheaper path.
    var canUseLayerInstructions: Bool {
        guard screenCrop == nil, effects == nil, style.isPlainRectangle else { return false }
        guard let overlay, let camera = overlay.probe?.displaySize, camera.height > 0 else { return true }

        let cameraAspect = camera.width / camera.height
        return overlay.keyframes.allSatisfy { keyframe in
            guard keyframe.visible else { return true }
            let rect = keyframe.rect.scaled(to: renderSize)
            guard rect.height > 0 else { return true }
            return abs(rect.width / rect.height - cameraAspect) / cameraAspect < 0.02
        }
    }
}
