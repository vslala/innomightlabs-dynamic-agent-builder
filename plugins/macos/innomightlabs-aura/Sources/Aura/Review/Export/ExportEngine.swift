import AVFoundation
import Foundation

enum ExportProgress: Equatable, Sendable {
    case preparing
    case exporting(fraction: Double)
}

/// Writes a built composition to a single file.
///
/// A protocol with one implementation today. `AVAssetReaderVideoCompositionOutput` and
/// `AVAssetReaderAudioMixOutput` accept the *same* `AVVideoComposition` and `AVAudioMix`, so
/// an `AVAssetWriter` path with explicit bitrate control is a second implementation rather
/// than a rewrite — which is the escape hatch if generational HEVC loss on screen text
/// becomes a complaint.
@MainActor
protocol ExportEngine {
    func export(
        _ composition: BuiltComposition,
        as format: ExportFormat,
        to url: URL,
        onProgress: @escaping (ExportProgress) -> Void
    ) async throws
}

enum ExportError: Error, LocalizedError {
    case unsupportedConfiguration

    var errorDescription: String? {
        switch self {
        case .unsupportedConfiguration:
            return "This recording can't be exported in that format."
        }
    }
}

@MainActor
struct AVAssetExportEngine: ExportEngine {
    func export(
        _ composition: BuiltComposition,
        as format: ExportFormat,
        to url: URL,
        onProgress: @escaping (ExportProgress) -> Void
    ) async throws {
        let presetName = switch format {
        // Quality-based rather than one of the fixed-size HEVC presets, which produce the
        // preset's video size and would rescale or letterbox a screen-native render size.
        case .video: AVAssetExportPresetHEVCHighestQuality
        // No video composition, no video encode: an asset with no video track cannot be
        // exported with a video preset at all — the session reports unsupported.
        case .audio: AVAssetExportPresetAppleM4A
        }
        guard let session = AVAssetExportSession(asset: composition.asset, presetName: presetName) else {
            throw ExportError.unsupportedConfiguration
        }

        if case .video = format {
            session.videoComposition = composition.videoComposition
        }
        session.audioMix = composition.audioMix
        session.timeRange = CMTimeRange(start: .zero, duration: composition.duration)
        session.shouldOptimizeForNetworkUse = true
        // Two passes roughly doubles the time for a marginal gain on this kind of content.
        session.canPerformMultiplePassesOverSourceMediaData = false

        try? FileManager.default.removeItem(at: url)
        onProgress(.preparing)

        // The state sequence reports progress *during* the export, so it has to be consumed
        // alongside it. The observer task is main-actor isolated, which is also what lets it
        // capture the export session — `AVAssetExportSession` is not Sendable, so it cannot
        // be handed to a task group's (sending) closures.
        let observer = Task { @MainActor in
            for await state in session.states(updateInterval: 0.25) {
                if case .exporting(let progress) = state {
                    onProgress(.exporting(fraction: progress.fractionCompleted))
                }
            }
        }
        defer { observer.cancel() }

        // Cancellation runs through Task.cancel(): the async overload already wraps the work
        // in a cancellation handler that calls cancelExport().
        try await session.export(to: url, as: format.fileType)
    }
}
