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

/// A word removed from the video, kept rather than deleted so it can be brought back.
///
/// Carries its resolved span in **session time** as well as its id, which keeps `edit.json`
/// self-contained: playback and export never need the transcript to know what was cut, while
/// the id remains the handle the user or the agent uses to restore it. `text` is stored so the
/// UI can show what was removed, and so the document reads intelligibly on its own.
struct ExcludedWord: Codable, Hashable, Sendable, Identifiable {
    var id: Int
    var start: TimeInterval
    var end: TimeInterval
    var text: String

    var span: TimeSpan { TimeSpan(start: start, end: end) }
}

/// Where the camera sits at a point in time. Keyframes are step-interpolated: a keyframe
/// holds until the next one, which is what lets the camera be hidden for one stretch of the
/// recording and visible for another.
struct OverlayKeyframe: Codable, Hashable, Sendable {
    /// `t` is the identity. Keyframes are kept at least one frame apart (see
    /// `EditOperation.keyframeTolerance`), so no two can round to the same displayed time —
    /// which is what previously made a pair at 84.5 and 84.5001 impossible to address.
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
    /// Manual A/V slip in seconds; positive plays this lane later. Applied on top of the
    /// automatic correction derived from the recorded track start offsets, and exists for the
    /// cases automation can't cover: recordings made before those offsets were logged, and
    /// residual device latency the user can hear but nothing can measure.
    var offset: TimeInterval

    init(lane: AudioLane, muted: Bool = false, gain: [GainKeyframe] = [], offset: TimeInterval = 0) {
        self.lane = lane
        self.muted = muted
        self.gain = gain
        self.offset = offset
    }

    private enum CodingKeys: String, CodingKey {
        case lane, muted, gain, offset
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        lane = try container.decode(AudioLane.self, forKey: .lane)
        muted = try container.decode(Bool.self, forKey: .muted)
        gain = try container.decode([GainKeyframe].self, forKey: .gain)
        // Optional so documents written before slip existed still load.
        offset = try container.decodeIfPresent(TimeInterval.self, forKey: .offset) ?? 0
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
    /// How the camera overlay is drawn. Beyond a plain rectangle this selects the Core Image
    /// compositor, so it lives in the document rather than being a view-level preference.
    var cameraStyle: PiPStyle

    /// Words cut from the video, reversibly. Separate from `clips` so a word-level edit can be
    /// undone individually and out of order — restoring one word months later shouldn't mean
    /// unwinding every edit made after it.
    var excludedWords: [ExcludedWord]

    private enum CodingKeys: String, CodingKey {
        case schemaVersion, micTimeOffset, clips, cameraOverlay, audioLanes, excludedWords, cameraStyle
    }

    init(
        schemaVersion: Int,
        micTimeOffset: TimeInterval,
        clips: [TimelineClip],
        cameraOverlay: [OverlayKeyframe],
        audioLanes: [AudioLaneSettings],
        excludedWords: [ExcludedWord],
        cameraStyle: PiPStyle = .plain
    ) {
        self.cameraStyle = cameraStyle
        self.schemaVersion = schemaVersion
        self.micTimeOffset = micTimeOffset
        self.clips = clips
        self.cameraOverlay = cameraOverlay
        self.audioLanes = audioLanes
        self.excludedWords = excludedWords
    }

    /// Hand-written so that a document saved before word exclusions existed still loads.
    /// Swift's synthesized decoder requires every non-optional key regardless of defaults, so
    /// relying on it here would have thrown away a user's existing edits on upgrade.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decode(Int.self, forKey: .schemaVersion)
        micTimeOffset = try container.decodeIfPresent(TimeInterval.self, forKey: .micTimeOffset) ?? 0
        clips = try container.decode([TimelineClip].self, forKey: .clips)
        cameraOverlay = try container.decode([OverlayKeyframe].self, forKey: .cameraOverlay)
        audioLanes = try container.decode([AudioLaneSettings].self, forKey: .audioLanes)
        excludedWords = try container.decodeIfPresent([ExcludedWord].self, forKey: .excludedWords) ?? []
        cameraStyle = try container.decodeIfPresent(PiPStyle.self, forKey: .cameraStyle) ?? .plain
    }

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
            audioLanes: AudioLane.allCases.map { AudioLaneSettings(lane: $0) },
            excludedWords: []
        )
    }

    /// What actually plays: the coarse clip list with every excluded word subtracted.
    ///
    /// Two independent layers rather than one, because they are edited differently — clips by
    /// dragging and cutting ranges, words by name — and collapsing them would make word
    /// removal destructive.
    var effectiveClips: [TimelineClip] {
        guard !excludedWords.isEmpty else { return clips }

        var result = clips
        for word in excludedWords.sorted(by: { $0.start < $1.start }) where !word.span.isEmpty {
            result = Self.subtracting(word.span, from: result)
        }
        return result
    }

    var timeMap: TimeMap { TimeMap(clips: effectiveClips) }

    func isExcluded(wordID: Int) -> Bool {
        excludedWords.contains { $0.id == wordID }
    }

    /// Lenient span subtraction, for composing word exclusions. Unlike the `removeRange`
    /// operation this never rejects: a word outside the surviving clips simply removes
    /// nothing, which is the right behaviour when a coarse cut already covered it.
    static func subtracting(_ span: TimeSpan, from clips: [TimelineClip]) -> [TimelineClip] {
        clips.flatMap { clip -> [TimelineClip] in
            let source = clip.source
            guard span.start < source.end, span.end > source.start else { return [clip] }

            var pieces: [TimelineClip] = []
            if span.start > source.start {
                pieces.append(TimelineClip(id: clip.id, source: TimeSpan(start: source.start, end: span.start)))
            }
            if span.end < source.end {
                let id = pieces.isEmpty ? clip.id : UUID()
                pieces.append(TimelineClip(id: id, source: TimeSpan(start: span.end, end: source.end)))
            }
            return pieces
        }
    }

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

    func offset(for lane: AudioLane) -> TimeInterval {
        settings(for: lane).offset
    }

    func gain(for lane: AudioLane, at t: TimeInterval) -> Double {
        let settings = settings(for: lane)
        if settings.muted { return 0 }
        let sorted = settings.gain.sorted { $0.t < $1.t }
        return sorted.last { $0.t <= t }?.gain ?? 1
    }
}
