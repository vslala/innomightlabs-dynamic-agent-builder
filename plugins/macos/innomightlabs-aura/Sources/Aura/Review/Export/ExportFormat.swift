import AVFoundation
import UniformTypeIdentifiers

/// What a session exports as. Derived from the timeline, not from the recording profile: a
/// screen recording whose video track came back empty must export as audio too, or the export
/// fails on an asset with nothing to encode.
enum ExportFormat: Equatable, Sendable {
    case video
    case audio

    init(timeline: ResolvedTimeline) {
        self = timeline.hasVideo ? .video : .audio
    }

    var fileExtension: String {
        switch self {
        case .video: return "mp4"
        case .audio: return "m4a"
        }
    }

    var contentType: UTType {
        switch self {
        case .video: return .mpeg4Movie
        case .audio: return .mpeg4Audio
        }
    }

    var fileType: AVFileType {
        switch self {
        case .video: return .mp4
        case .audio: return .m4a
        }
    }
}
