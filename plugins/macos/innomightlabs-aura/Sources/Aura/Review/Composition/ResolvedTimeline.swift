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

struct ResolvedVideoLayer: Equatable, Sendable {
    let probe: SourceTrackProbe
    /// Non-empty, sorted, deduplicated, and guaranteed to start at composition time zero.
    let keyframes: [ResolvedOverlayKeyframe]
    /// How much later this file's content plays than its own timeline implies. See
    /// `SourceTrackProbe.alignmentCorrection`.
    let timeOffset: CMTime
}

struct ResolvedAudioLane: Equatable, Sendable {
    let lane: AudioLane
    let probe: SourceTrackProbe
    /// Non-empty, sorted, deduplicated, and guaranteed to start at composition time zero.
    let keyframes: [ResolvedGainKeyframe]
    /// The automatic alignment correction plus the user's manual slip.
    let timeOffset: CMTime
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

    var duration: CMTime { timeMap.cmDuration }
    var hasVideo: Bool { base != nil }
}
