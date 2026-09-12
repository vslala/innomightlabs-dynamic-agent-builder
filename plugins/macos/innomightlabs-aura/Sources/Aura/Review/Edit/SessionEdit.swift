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

/// One surviving stretch of the recording. `source` is on the session timeline — the
/// pause-compacted clock all four recorded files share.
///
/// Deliberately identity-free. The old `id` was write-only (set on every derivation, read by
/// nobody), and regenerating it made `TimeMap == TimeMap` false for identical timelines, which
/// defeated the `.equatable()` short-circuit that stops the waveform re-rasterising on every
/// publish.
struct TimelineClip: Codable, Hashable, Sendable {
    var source: TimeSpan

    init(source: TimeSpan) {
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

/// One removal from the recording, addressable and individually reversible.
///
/// Cuts are *facts about the original recording*, not mutations of a clip list — which is what
/// lets a single cut be pointed at, shaded on the waveform, and restored on its own. Two cuts
/// may legitimately cover the same region (a word cut inside a coarse range cut), so anything
/// resolving a point back to cuts must handle several.
struct Cut: Identifiable, Codable, Hashable, Sendable {
    /// Why this was cut, which is what the UI labels and what restoration means.
    enum Origin: Codable, Hashable, Sendable {
        /// A range the user selected directly.
        case range
        /// One transcript word. Carries the word's identity so the span can be re-derived.
        case word(id: Int, text: String)
        /// Part of a filler sweep.
        case filler(word: String)
        /// Proposed by the agent and accepted.
        case agent(reason: String)
    }

    let id: UUID
    /// Session time.
    var span: TimeSpan
    var origin: Origin

    init(id: UUID = UUID(), span: TimeSpan, origin: Origin) {
        self.id = id
        self.span = span
        self.origin = origin
    }

    var isFiller: Bool {
        if case .filler = origin { return true }
        return false
    }

    var wordID: Int? {
        if case .word(let id, _) = origin { return id }
        return nil
    }

    /// A one-word tag for the agent digest, which has no room for the associated values.
    var digestLabel: String {
        switch origin {
        case .range: return "user"
        case .word: return "word"
        case .filler: return "filler"
        case .agent: return "agent"
        }
    }

    /// What was removed, for labelling a shaded region or a suggestion.
    var text: String? {
        switch origin {
        case .word(_, let text): return text
        case .filler(let word): return word
        case .range, .agent: return nil
        }
    }
}

/// A point the user marked while editing, as distinct from a marker logged during recording.
///
/// Recording markers live in `events.jsonl` and are immutable facts; these are editorial and
/// can be moved, renamed and deleted.
struct EditMarker: Identifiable, Codable, Hashable, Sendable {
    let id: UUID
    /// Session time.
    var at: TimeInterval
    var label: String

    init(id: UUID = UUID(), at: TimeInterval, label: String = "") {
        self.id = id
        self.at = at
        self.label = label
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

/// The non-destructive edit document, persisted as `edit.json`.
///
/// **Declarative.** It records what was *removed* from the original recording, not what
/// survives: `cuts` plus `splitPoints`, from which the surviving clip list is derived. That
/// inversion is what makes every cut addressable and individually restorable, and it means
/// there is one definition of the timeline rather than a clip list and an exclusion list that
/// can disagree.
///
/// Contains no AVFoundation types: it is also the shape the InnomightLabs agent reads, and the
/// shape `EditOperation`s mutate. Compositions are derived from it and never the other way
/// round.
struct SessionEdit: Codable, Equatable, Sendable {
    /// v2 made the document declarative: `cuts`/`splitPoints`/`markers` replaced a mutable
    /// clip list and a separate word-exclusion list. A v1 document is migrated by
    /// `SessionEditMigration`, never decoded directly — see there for why.
    static let currentSchemaVersion = 2

    var schemaVersion: Int
    /// The original recording's full extent, in session time.
    ///
    /// Stored rather than measured from the media on each open. Three places need the extent
    /// and have no probes — `applying(_:)` (pure by design, and where the "would remove
    /// everything" guard lives), `SessionDigest.make`, and `EditSuggestionPrompt.build` — and
    /// probing is not even stable: a moved or truncated file probes as absent, which would
    /// silently shorten the timeline and discard edits beyond the new end.
    var recordingDuration: TimeInterval
    /// Removals. Never merged here, only when deriving clips: merging would destroy the
    /// individual restorability that is the point of storing them separately.
    var cuts: [Cut]
    /// Boundaries that remove nothing. Deliberately **not** part of the derived timeline —
    /// see `clips`.
    var splitPoints: [TimeInterval]
    /// Editorial markers, distinct from the recording markers in `events.jsonl`.
    var markers: [EditMarker]
    /// Seconds between the session timeline and mic media time. The transcript is produced
    /// from `microphone.m4a`, so it is stamped in mic media time; if the mic writer had
    /// warm-up latency the two clocks differ by 100-300ms.
    var micTimeOffset: TimeInterval
    var cameraOverlay: [OverlayKeyframe]
    var audioLanes: [AudioLaneSettings]
    /// How the camera overlay is drawn. Beyond a plain rectangle this selects the Core Image
    /// compositor, so it lives in the document rather than being a view-level preference.
    var cameraStyle: PiPStyle
    /// Identifies the transcript the `.word` cuts were made against.
    ///
    /// Word ids are renumbered densely per transcript file, so re-transcribing invalidates
    /// them. Without this, the span-repair pass would rewrite cuts onto whichever words now
    /// hold those ids — turning a safety net into a corruption mechanism.
    var transcriptIdentity: String?
    /// What the user calls this recording. Nil until renamed, so the UI can fall back to
    /// something derived from the capture date rather than persisting a default it would then
    /// have to distinguish from a real choice.
    var name: String?

    private enum CodingKeys: String, CodingKey {
        case schemaVersion, recordingDuration, cuts, splitPoints, markers
        case micTimeOffset, cameraOverlay, audioLanes, cameraStyle, transcriptIdentity, name
    }

    init(
        schemaVersion: Int = currentSchemaVersion,
        recordingDuration: TimeInterval,
        cuts: [Cut] = [],
        splitPoints: [TimeInterval] = [],
        markers: [EditMarker] = [],
        micTimeOffset: TimeInterval = 0,
        cameraOverlay: [OverlayKeyframe],
        audioLanes: [AudioLaneSettings],
        cameraStyle: PiPStyle = .plain,
        transcriptIdentity: String? = nil,
        name: String? = nil
    ) {
        self.schemaVersion = schemaVersion
        self.recordingDuration = recordingDuration
        self.cuts = cuts
        self.splitPoints = splitPoints
        self.markers = markers
        self.micTimeOffset = micTimeOffset
        self.cameraOverlay = cameraOverlay
        self.audioLanes = audioLanes
        self.cameraStyle = cameraStyle
        self.transcriptIdentity = transcriptIdentity
        self.name = name
    }

    /// Strict about the two keys that define the timeline.
    ///
    /// `cuts` and `recordingDuration` are **required**, unlike the tolerant defaults used for
    /// additive fields. Defaulting them would mean a v2 document that somehow lost `cuts`
    /// decodes as "nothing was cut" and silently discards every edit — which is precisely the
    /// failure the hand-written decoder exists to prevent. A v1 document is routed to
    /// `SessionEditMigration` before it ever reaches here.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decode(Int.self, forKey: .schemaVersion)
        recordingDuration = try container.decode(TimeInterval.self, forKey: .recordingDuration)
        cuts = try container.decode([Cut].self, forKey: .cuts)
        splitPoints = try container.decodeIfPresent([TimeInterval].self, forKey: .splitPoints) ?? []
        markers = try container.decodeIfPresent([EditMarker].self, forKey: .markers) ?? []
        micTimeOffset = try container.decodeIfPresent(TimeInterval.self, forKey: .micTimeOffset) ?? 0
        cameraOverlay = try container.decode([OverlayKeyframe].self, forKey: .cameraOverlay)
        audioLanes = try container.decode([AudioLaneSettings].self, forKey: .audioLanes)
        cameraStyle = try container.decodeIfPresent(PiPStyle.self, forKey: .cameraStyle) ?? .plain
        transcriptIdentity = try container.decodeIfPresent(String.self, forKey: .transcriptIdentity)
        name = try container.decodeIfPresent(String.self, forKey: .name)
    }

    /// A fresh document for an unedited recording: nothing cut, the camera parked in a corner,
    /// both lanes at unity gain.
    static func initial(
        duration: TimeInterval,
        micTimeOffset: TimeInterval = 0,
        cameraRect: NormalizedRect = .defaultCameraOverlay,
        cameraVisible: Bool = true
    ) -> SessionEdit {
        SessionEdit(
            recordingDuration: max(0, duration),
            micTimeOffset: micTimeOffset,
            cameraOverlay: [OverlayKeyframe(t: 0, rect: cameraRect, visible: cameraVisible)],
            audioLanes: AudioLane.allCases.map { AudioLaneSettings(lane: $0) }
        )
    }

    // MARK: - Derived timeline

    /// What actually plays: the recording minus every cut.
    ///
    /// Derived from **cuts only**. `splitPoints` are deliberately excluded: nothing yet moves,
    /// trims or reorders clips, so a split that removes nothing would add a composition
    /// segment, an extra `insertTimeRange` per track, and another boundary at which
    /// AVFoundation picks the nearest decodable frame — visibly duplicating or dropping a
    /// frame for byte-identical output. Splits stay an editing concern (drawn on the ruler,
    /// used to bound selections) until trim or move lands.
    var clips: [TimelineClip] {
        Self.deriveClips(recordingDuration: recordingDuration, cuts: cuts)
    }

    var timeMap: TimeMap { TimeMap(clips: clips) }

    /// Total played duration: the recording minus what was cut.
    var duration: TimeInterval { timeMap.duration }

    /// Cuts merged into disjoint, ascending ranges. Merging happens **only** here.
    static func mergedCutRanges(_ cuts: [Cut], recordingDuration: TimeInterval) -> [CMTimeRange] {
        let limit = Timeline.time(seconds: max(0, recordingDuration))
        guard limit > .zero else { return [] }

        let ranges = cuts
            .compactMap { cut -> CMTimeRange? in
                guard cut.span.start.isFinite, cut.span.end.isFinite else { return nil }
                let start = max(.zero, Timeline.time(seconds: cut.span.start))
                let end = min(limit, Timeline.time(seconds: cut.span.end))
                guard end > start else { return nil }
                return CMTimeRange(start: start, end: end)
            }
            .sorted { lhs, rhs in
                lhs.start == rhs.start ? lhs.end < rhs.end : lhs.start < rhs.start
            }

        var merged: [CMTimeRange] = []
        for range in ranges {
            // `<=` so touching cuts merge too; otherwise the derivation emits zero-length
            // clips between them.
            if let last = merged.last, range.start <= last.end {
                merged[merged.count - 1] = CMTimeRange(start: last.start, end: max(last.end, range.end))
            } else {
                merged.append(range)
            }
        }
        return merged
    }

    /// `[0, duration]` minus the merged cuts, in one forward sweep.
    static func deriveClips(recordingDuration: TimeInterval, cuts: [Cut]) -> [TimelineClip] {
        let limit = Timeline.time(seconds: max(0, recordingDuration))
        guard limit > .zero else { return [] }

        var result: [TimelineClip] = []
        var cursor = CMTime.zero

        for cut in mergedCutRanges(cuts, recordingDuration: recordingDuration) {
            if cut.start > cursor {
                result.append(TimelineClip(source: TimeSpan(CMTimeRange(start: cursor, end: cut.start))))
            }
            cursor = max(cursor, cut.end)
        }
        if cursor < limit {
            result.append(TimelineClip(source: TimeSpan(CMTimeRange(start: cursor, end: limit))))
        }
        return result
    }

    // MARK: - Cuts

    func cut(id: UUID) -> Cut? { cuts.first { $0.id == id } }

    /// Every cut covering a point in session time — plural, because a word cut can sit inside
    /// a range cut, so restoring only one of them would visibly do nothing.
    func cuts(at time: TimeInterval) -> [Cut] {
        cuts.filter { $0.span.contains(time) }
    }

    func isExcluded(wordID: Int) -> Bool {
        cuts.contains { $0.wordID == wordID }
    }

    /// The word cuts, in the shape the agent and the transcript panel already expect.
    var excludedWords: [ExcludedWord] {
        cuts.compactMap { cut in
            guard case .word(let id, let text) = cut.origin else { return nil }
            return ExcludedWord(id: id, start: cut.span.start, end: cut.span.end, text: text)
        }
        .sorted { $0.start < $1.start }
    }

    // MARK: - Lookups

    func settings(for lane: AudioLane) -> AudioLaneSettings {
        audioLanes.first { $0.lane == lane } ?? AudioLaneSettings(lane: lane)
    }

    func offset(for lane: AudioLane) -> TimeInterval {
        settings(for: lane).offset
    }

    /// The overlay state in force at a **session** time. Returns the last keyframe at or
    /// before `t`, falling back to the first so there is always an answer — leaving the camera
    /// layer without an explicit transform makes AVFoundation render it full-size in the
    /// top-left corner.
    func overlay(at t: TimeInterval) -> OverlayKeyframe? {
        let sorted = cameraOverlay.sorted { $0.t < $1.t }
        return sorted.last { $0.t <= t } ?? sorted.first
    }

    /// Linear gain for a lane at a **session** time.
    func gain(for lane: AudioLane, at t: TimeInterval) -> Double {
        let settings = settings(for: lane)
        if settings.muted { return 0 }
        let sorted = settings.gain.sorted { $0.t < $1.t }
        return sorted.last { $0.t <= t }?.gain ?? 1
    }
}
