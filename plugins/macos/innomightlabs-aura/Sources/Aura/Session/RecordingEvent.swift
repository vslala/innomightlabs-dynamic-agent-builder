import Foundation

enum RecordingEventKind: String, Codable {
    case recordStart = "record_start"
    case pause
    case resume
    case recordStop = "record_stop"
    case userMarker = "user_marker"
    case screenSnapshot = "screen_snapshot"
    case trackFailed = "track_failed"
    case trackStart = "track_start"
    /// Diagnostic only. The composition layer learns what a session recorded from the files
    /// on disk, never from this — see `RecordingManifest`'s doc comment for why.
    case profileChanged = "profile_changed"
    /// Diagnostic only, logged once per track at retirement — never per frame, which would
    /// itself become a performance problem under the load that causes drops in the first
    /// place. See `TrackWriter.droppedSampleCount` and `CaptureSource.droppedFrameCount`.
    case framesDropped = "frames_dropped"
}

struct RecordingEvent: Codable, Equatable {
    /// Wall-clock seconds since record start, including any paused time. Kept as a
    /// faithful record of when things actually happened.
    let ts: TimeInterval
    let type: RecordingEventKind
    /// Seconds on the pause-compacted timeline the media files use — the clock the review
    /// window plays back on. Absent in logs written before this field existed;
    /// `EventTimeline` recovers it from the pause/resume events in that case.
    var mediaTs: TimeInterval? = nil
    var app: String? = nil
    var label: String? = nil
    var path: String? = nil

    private enum CodingKeys: String, CodingKey {
        case ts, type, app, label, path
        case mediaTs = "media_ts"
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(ts, forKey: .ts)
        try container.encode(type, forKey: .type)
        try container.encodeIfPresent(mediaTs, forKey: .mediaTs)
        try container.encodeIfPresent(app, forKey: .app)
        try container.encodeIfPresent(label, forKey: .label)
        try container.encodeIfPresent(path, forKey: .path)
    }
}
