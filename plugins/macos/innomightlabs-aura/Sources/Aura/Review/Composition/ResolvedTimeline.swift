import CoreMedia
import Foundation

/// Cosmetic PiP treatment. Carried here now and **ignored** by
/// `LayerInstructionCompositionBuilder`, whose compositor supports only an affine transform,
/// opacity, and an axis-aligned crop. When a custom compositor lands it reads these and
/// nothing upstream — `edit.json`, `EditOperation`, the UI — has to change.
struct PiPStyle: Codable, Hashable, Sendable {
    var cornerRadius: Double
    var borderWidth: Double
    var shadowOpacity: Double

    static let plain = PiPStyle(cornerRadius: 0, borderWidth: 0, shadowOpacity: 0)
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
