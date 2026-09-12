import AVFoundation
import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

/// Pulls thumbnails out of a video track.
///
/// An `actor` because `AVAssetImageGenerator` is not `Sendable` and serializes internally
/// anyway — one generator per extraction, owned by one isolation domain.
actor FilmstripExtractor {
    /// Extracts a strip, or nil if the asset has no usable video.
    ///
    /// Tolerances are `.positiveInfinity` deliberately: a filmstrip wants the nearest keyframe,
    /// and demanding exact frames from a long HEVC screen capture is orders of magnitude slower
    /// for a thumbnail nobody inspects frame-accurately.
    func extract(from url: URL, duration: TimeInterval) async -> Filmstrip? {
        let asset = AVURLAsset(
            url: url,
            options: [AVURLAssetPreferPreciseDurationAndTimingKey: true]
        )

        guard
            let track = try? await asset.loadTracks(withMediaType: .video).first,
            let trackDuration = try? await track.load(.timeRange).duration,
            trackDuration.isNumeric, trackDuration > .zero
        else { return nil }

        let usable = min(duration > 0 ? duration : .greatestFiniteMagnitude,
                         Timeline.seconds(trackDuration))
        let plan = Filmstrip.plan(duration: usable)
        guard plan.count > 0 else { return nil }

        let generator = AVAssetImageGenerator(asset: asset)
        generator.appliesPreferredTrackTransform = true
        generator.maximumSize = Filmstrip.extractionSize
        generator.requestedTimeToleranceBefore = .positiveInfinity
        generator.requestedTimeToleranceAfter = .positiveInfinity

        let times = (0..<plan.count).map { index in
            Timeline.time(seconds: (Double(index) + 0.5) * plan.interval)
        }

        var frames: [Data] = []
        frames.reserveCapacity(plan.count)
        var frameSize = Filmstrip.extractionSize

        for await result in generator.images(for: times) {
            if Task.isCancelled { return nil }
            guard let image = try? result.image else { continue }
            frameSize = CGSize(width: image.width, height: image.height)
            guard let jpeg = Self.jpeg(from: image) else { continue }
            frames.append(jpeg)
        }

        guard !frames.isEmpty else { return nil }
        return Filmstrip(interval: plan.interval, frameSize: frameSize, frames: frames)
    }

    /// JPEG rather than PNG: these are photographic thumbnails where PNG would be several
    /// times larger for no visible gain at 160px.
    private static func jpeg(from image: CGImage, quality: CGFloat = 0.72) -> Data? {
        let data = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(
            data, UTType.jpeg.identifier as CFString, 1, nil
        ) else { return nil }

        CGImageDestinationAddImage(destination, image, [
            kCGImageDestinationLossyCompressionQuality: quality
        ] as CFDictionary)

        guard CGImageDestinationFinalize(destination) else { return nil }
        return data as Data
    }
}
