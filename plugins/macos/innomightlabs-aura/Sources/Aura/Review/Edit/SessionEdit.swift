import CoreMedia
import Foundation

/// A half-open span `[start, end)` in seconds. Half-open is what keeps a cut boundary
/// belonging to exactly one clip.
struct TimeSpan: Codable, Hashable, Sendable {
    var start: TimeInterval
    var end: TimeInterval

    var duration: TimeInterval { max(0, end - start) }
    var isEmpty: Bool { end <= start }

    var cmRange: CMTimeRange {
        CMTimeRange(start: Timeline.time(seconds: start), end: Timeline.time(seconds: end))
    }

    init(start: TimeInterval, end: TimeInterval) {
        self.start = start
        self.end = end
    }

    init(_ range: CMTimeRange) {
        start = Timeline.seconds(range.start)
        end = Timeline.seconds(range.end)
    }

    func contains(_ t: TimeInterval) -> Bool { t >= start && t < end }
}

/// One entry in the edit decision list. `source` is on the session timeline — the
/// pause-compacted clock all four recorded files share.
struct TimelineClip: Codable, Hashable, Sendable, Identifiable {
    var id: UUID
    var source: TimeSpan

    init(id: UUID = UUID(), source: TimeSpan) {
        self.id = id
        self.source = source
    }
}

/// A rect normalized against the render size, top-left origin — so a layout survives a
/// change of output resolution, and the preview and the export agree.
struct NormalizedRect: Codable, Hashable, Sendable {
    var x: Double
    var y: Double
    var width: Double
    var height: Double

    static let defaultCameraOverlay = NormalizedRect(x: 0.72, y: 0.70, width: 0.25, height: 0.25)

    var isValid: Bool {
        [x, y, width, height].allSatisfy(\.isFinite) && width > 0 && height > 0
    }

    func scaled(to size: CGSize) -> CGRect {
        CGRect(x: x * size.width, y: y * size.height, width: width * size.width, height: height * size.height)
    }
}

/// Where the camera sits at a point in time. Keyframes are step-interpolated: a keyframe
/// holds until the next one, which is what lets the camera be hidden for one stretch of the
/// recording and visible for another.
struct OverlayKeyframe: Codable, Hashable, Sendable {
    var t: TimeInterval
    var rect: NormalizedRect
    var visible: Bool
}

enum AudioLane: String, Codable, CaseIterable, Sendable {
    case microphone
    case systemAudio = "system_audio"
}

struct GainKeyframe: Codable, Hashable, Sendable {
    var t: TimeInterval
    /// Linear volume, matching `AVAudioMixInputParameters` semantics.
    var gain: Double
}

/// The two audio sources stay separate all the way through export, because
/// `AVMutableAudioMixInputParameters` is per-track — separate tracks is what makes
/// independent gain and mute expressible at all.
struct AudioLaneSettings: Codable, Hashable, Sendable {
    var lane: AudioLane
    var muted: Bool
    var gain: [GainKeyframe]

    init(lane: AudioLane, muted: Bool = false, gain: [GainKeyframe] = []) {
        self.lane = lane
        self.muted = muted
        self.gain = gain
    }
}

/// The non-destructive edit document, persisted as `edit.json` beside the recorded files.
///
/// This is the single source of truth for the review window, and deliberately contains no
/// AVFoundation types: it is also the shape the InnomightLabs agent reads when suggesting
/// edits, and the shape `EditOperation`s mutate. Compositions are derived from it and never
/// the other way round.
struct SessionEdit: Codable, Equatable, Sendable {
    static let currentSchemaVersion = 1

    var schemaVersion: Int
    /// Seconds between the session timeline and mic media time. The transcript is produced
    /// from `microphone.m4a`, so it is stamped in mic media time; if the mic writer had
    /// warm-up latency that file carries a leading empty edit and the two clocks differ by
    /// 100-300ms. Resolved once at import and read from here by everything else.
    var micTimeOffset: TimeInterval
    var clips: [TimelineClip]
    var cameraOverlay: [OverlayKeyframe]
    var audioLanes: [AudioLaneSettings]

    /// A fresh document for an unedited recording: one clip spanning the whole thing, the
    /// camera parked in a corner, both lanes at unity gain.
    static func initial(
        duration: TimeInterval,
        micTimeOffset: TimeInterval = 0,
        cameraRect: NormalizedRect = .defaultCameraOverlay,
        cameraVisible: Bool = true
    ) -> SessionEdit {
        SessionEdit(
            schemaVersion: currentSchemaVersion,
            micTimeOffset: micTimeOffset,
            clips: [TimelineClip(source: TimeSpan(start: 0, end: max(0, duration)))],
            cameraOverlay: [OverlayKeyframe(t: 0, rect: cameraRect, visible: cameraVisible)],
            audioLanes: AudioLane.allCases.map { AudioLaneSettings(lane: $0) }
        )
    }

    var timeMap: TimeMap { TimeMap(clips: clips) }

    /// Total played duration, which is the sum of the clips rather than the recording length
    /// once anything has been cut.
    var duration: TimeInterval { timeMap.duration }

    func settings(for lane: AudioLane) -> AudioLaneSettings {
        audioLanes.first { $0.lane == lane } ?? AudioLaneSettings(lane: lane)
    }

    /// The overlay state in force at a composition time. Returns the last keyframe at or
    /// before `t`; falls back to the first keyframe so there is always an answer, because
    /// leaving the camera layer without an explicit transform makes AVFoundation render it
    /// full-size in the top-left corner.
    func overlay(at t: TimeInterval) -> OverlayKeyframe? {
        let sorted = cameraOverlay.sorted { $0.t < $1.t }
        return sorted.last { $0.t <= t } ?? sorted.first
    }

    func gain(for lane: AudioLane, at t: TimeInterval) -> Double {
        let settings = settings(for: lane)
        if settings.muted { return 0 }
        let sorted = settings.gain.sorted { $0.t < $1.t }
        return sorted.last { $0.t <= t }?.gain ?? 1
    }
}
