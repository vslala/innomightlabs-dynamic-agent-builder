import AVFoundation
import CoreMedia
import Foundation

/// A composition ready to hand to a player or an exporter.
///
/// The asset is an immutable snapshot, because mutating a composition after an export has
/// commenced is documented as undefined. Not `Sendable`: `AVAsset` isn't, and `AVPlayer` is
/// `@MainActor` anyway, so compositions are built and consumed in one isolation domain
/// rather than being forced across one with an unchecked conformance.
struct BuiltComposition {
    let asset: AVAsset
    let videoComposition: AVVideoComposition?
    let audioMix: AVAudioMix?
    let duration: CMTime
    let renderSize: CGSize
}

/// The seam between the edit model and AVFoundation.
///
/// `LayerInstructionCompositionBuilder` is the only implementation today. A
/// `CustomCompositorCompositionBuilder` reading `PiPStyle` for rounded corners, borders, and
/// shadows can replace it without `edit.json`, `EditOperation`, or the UI changing — only
/// which builder is constructed.
@MainActor
protocol CompositionBuilding {
    func build(_ timeline: ResolvedTimeline, maxRenderDimension: CGFloat?) async throws -> BuiltComposition
}

extension CompositionBuilding {
    func build(_ timeline: ResolvedTimeline) async throws -> BuiltComposition {
        try await build(timeline, maxRenderDimension: nil)
    }
}

enum CompositionError: Error, LocalizedError {
    case noUsableMedia

    var errorDescription: String? {
        switch self {
        case .noUsableMedia:
            return "This recording has no playable video or audio."
        }
    }
}
