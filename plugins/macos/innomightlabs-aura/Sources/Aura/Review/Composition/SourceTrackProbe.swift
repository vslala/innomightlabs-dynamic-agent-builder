import AVFoundation
import CoreMedia
import Foundation

enum TrackKind: String, Sendable, CaseIterable {
    case screen
    case camera
    case microphone
    case systemAudio

    var mediaType: AVMediaType {
        switch self {
        case .screen, .camera: return .video
        case .microphone, .systemAudio: return .audio
        }
    }

    var isVideo: Bool { mediaType == .video }

    var lane: AudioLane? {
        switch self {
        case .microphone: return .microphone
        case .systemAudio: return .systemAudio
        case .screen, .camera: return nil
        }
    }
}

/// What the review layer knows about one recorded file, reduced to Sendable value types.
///
/// `AVAsset` and `AVAssetTrack` are not Sendable, so primitives are extracted at the
/// boundary and nothing downstream ever holds an AVFoundation object. The geometry here is
/// always read from the written file rather than from what the recorder declared —
/// `CameraRecorder` reads `activeFormat` before the capture session applies its preset, so
/// its declared size can disagree with what actually got encoded.
struct SourceTrackProbe: Sendable, Equatable {
    let url: URL
    let kind: TrackKind
    let duration: CMTime
    /// Upright display size, i.e. `naturalSize` with `preferredTransform` applied. Nil for audio.
    let displaySize: CGSize?
    let preferredTransform: CGAffineTransform
    /// The track's colour tags, when it carries them. A video composition that leaves these
    /// nil propagates "the source's" colour space, which is ambiguous when a P3 display
    /// capture and a BT.709 camera are composited together and can hue-shift one layer.
    var colorPrimaries: String? = nil
    var colorTransferFunction: String? = nil
    var colorYCbCrMatrix: String? = nil
    /// Length of the leading empty edit, if the writer's first sample arrived after
    /// `startSession(atSourceTime:)`. It is what keeps the four files mutually aligned, so
    /// anything reading through AVFoundation's edit list needs no correction — but a decoder
    /// that reads the raw track instead (which is the usual shape for an ML audio pipeline)
    /// starts counting at the first real sample and is early by exactly this much.
    var leadingEmptyEdit: CMTime = .zero
    /// How far behind the session start this track's first sample actually was, as recorded
    /// at capture time. Zero for sessions recorded before that was logged.
    var recordedStartOffset: CMTime = .zero

    /// How much later this file's content must play than its own timeline implies.
    ///
    /// `AVAssetWriter` preserves a track's warm-up offset for video by inserting a leading
    /// empty edit, but for audio it slides the first sample to zero and drops the offset —
    /// so audio plays early by its entire startup delay, which is the A/V desync. Video
    /// therefore corrects by ~nothing (recorded and edit offsets agree) while audio corrects
    /// by the whole recorded offset.
    var alignmentCorrection: CMTime {
        let correction = recordedStartOffset - leadingEmptyEdit
        return correction > .zero ? Timeline.normalized(correction) : .zero
    }

    /// Pure. Uses `CGRect.applying` rather than `CGSize.applying`, which yields negative
    /// components for flip and rotate transforms.
    static func displaySize(naturalSize: CGSize, preferredTransform: CGAffineTransform) -> CGSize {
        let bounds = CGRect(origin: .zero, size: naturalSize).applying(preferredTransform)
        return CGSize(width: abs(bounds.width), height: abs(bounds.height))
    }

    /// Returns nil for a file that is absent, empty, or truncated. A writer that failed
    /// mid-recording leaves a file whose `moov` was never written, and its duration comes
    /// back non-numeric — so every track is optional as far as the review layer is concerned.
    static func probe(url: URL, kind: TrackKind) async -> SourceTrackProbe? {
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }

        // Precise timing costs a scan of a local file but is what makes `duration` exact and
        // `insertTimeRange` reliable.
        let asset = AVURLAsset(url: url, options: [AVURLAssetPreferPreciseDurationAndTimingKey: true])
        do {
            let duration = try await asset.load(.duration)
            guard duration.isNumeric, duration > .zero else { return nil }
            guard let track = try await asset.loadTracks(withMediaType: kind.mediaType).first else { return nil }

            let (naturalSize, transform, formats, segments) = try await track.load(
                .naturalSize, .preferredTransform, .formatDescriptions, .segments
            )
            let size = Self.displaySize(naturalSize: naturalSize, preferredTransform: transform)
            // A video track with no usable geometry has no frames worth compositing.
            if kind.isVideo, size.width < 1 || size.height < 1 { return nil }

            let format = formats.first
            return SourceTrackProbe(
                url: url,
                kind: kind,
                duration: Timeline.normalized(duration),
                displaySize: kind.isVideo ? size : nil,
                preferredTransform: transform,
                colorPrimaries: format.flatMap { Self.stringExtension($0, kCMFormatDescriptionExtension_ColorPrimaries) },
                colorTransferFunction: format.flatMap { Self.stringExtension($0, kCMFormatDescriptionExtension_TransferFunction) },
                colorYCbCrMatrix: format.flatMap { Self.stringExtension($0, kCMFormatDescriptionExtension_YCbCrMatrix) },
                leadingEmptyEdit: Self.leadingEmptyEdit(in: segments)
            )
        } catch {
            return nil
        }
    }

    static func leadingEmptyEdit(in segments: [AVAssetTrackSegment]) -> CMTime {
        guard let first = segments.first, first.isEmpty else { return .zero }
        let duration = first.timeMapping.target.duration
        return duration.isNumeric ? Timeline.normalized(duration) : .zero
    }

    private static func stringExtension(_ format: CMFormatDescription, _ key: CFString) -> String? {
        CMFormatDescriptionGetExtension(format, extensionKey: key) as? String
    }

    static func probeAll(in folder: SessionFolder) async -> [SourceTrackProbe] {
        let sources: [(URL, TrackKind)] = [
            (folder.screenURL, .screen),
            (folder.cameraURL, .camera),
            (folder.microphoneURL, .microphone),
            (folder.systemAudioURL, .systemAudio)
        ]
        let recordedOffsets = EventTimeline.load(eventsURL: folder.eventsURL).trackStartOffsets

        var probes: [SourceTrackProbe] = []
        for (url, kind) in sources {
            guard var probe = await probe(url: url, kind: kind) else { continue }
            if let offset = recordedOffsets[kind.rawValue] {
                probe.recordedStartOffset = Timeline.time(seconds: offset)
            }
            probes.append(probe)
        }
        return probes
    }
}
