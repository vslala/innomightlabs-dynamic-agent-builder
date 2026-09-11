import Foundation

/// The only way a `SessionEdit` changes.
///
/// This is the extensibility seam of the whole review layer: a mouse drag produces one of
/// these today, and the InnomightLabs agent and voice control will produce exactly the same
/// ones later. So the JSON encoding here is a contract, not an implementation detail — it is
/// hand-written with an `op` discriminator and flat fields rather than left to the synthesized
/// enum form, which would nest payloads under `_0`.
///
/// **Every time in an operation is session time** — the pause-compacted clock the recorded
/// files and the transcript share, not the composition/playhead clock. That keeps edits
/// anchored to content: an overlay change stays with the moment it was authored against even
/// after an earlier range is cut, and an agent reasoning from transcript timestamps can emit
/// operations directly. The UI converts its playhead through `TimeMap` at the boundary.
enum EditOperation: Codable, Equatable, Sendable {
    case removeRange(TimeSpan)
    case splitClip(at: TimeInterval)
    case setOverlayKeyframe(OverlayKeyframe)
    case removeOverlayKeyframe(at: TimeInterval)
    case setLaneGain(lane: AudioLane, keyframe: GainKeyframe)
    case setLaneMuted(lane: AudioLane, muted: Bool)
    case setLaneOffset(lane: AudioLane, seconds: TimeInterval)
    /// Cut individual words, reversibly. Spans are resolved from the transcript before the
    /// operation is built, so the document never needs the transcript to play back.
    case excludeWords([ExcludedWord])
    /// Bring excluded words back, by id and in any order.
    case restoreWords(ids: [Int])
    /// Shape, border, and shadow for the camera overlay.
    case setCameraStyle(PiPStyle)

    private enum Op: String, Codable {
        case removeRange = "remove_range"
        case splitClip = "split_clip"
        case setOverlayKeyframe = "set_overlay_keyframe"
        case removeOverlayKeyframe = "remove_overlay_keyframe"
        case setLaneGain = "set_lane_gain"
        case setLaneMuted = "set_lane_muted"
        case setLaneOffset = "set_lane_offset"
        case excludeWords = "exclude_words"
        case restoreWords = "restore_words"
        case setCameraStyle = "set_camera_style"
    }

    private enum CodingKeys: String, CodingKey {
        case op, start, end, t, rect, visible, lane, gain, muted, seconds, words, ids
        case shape, cornerRadius, borderWidth, borderColor, shadowOpacity, shadowRadius
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        switch try container.decode(Op.self, forKey: .op) {
        case .removeRange:
            self = .removeRange(TimeSpan(
                start: try container.decode(TimeInterval.self, forKey: .start),
                end: try container.decode(TimeInterval.self, forKey: .end)
            ))
        case .splitClip:
            self = .splitClip(at: try container.decode(TimeInterval.self, forKey: .t))
        case .setOverlayKeyframe:
            self = .setOverlayKeyframe(OverlayKeyframe(
                t: try container.decode(TimeInterval.self, forKey: .t),
                rect: try container.decode(NormalizedRect.self, forKey: .rect),
                visible: try container.decodeIfPresent(Bool.self, forKey: .visible) ?? true
            ))
        case .removeOverlayKeyframe:
            self = .removeOverlayKeyframe(at: try container.decode(TimeInterval.self, forKey: .t))
        case .setLaneGain:
            self = .setLaneGain(
                lane: try container.decode(AudioLane.self, forKey: .lane),
                keyframe: GainKeyframe(
                    t: try container.decode(TimeInterval.self, forKey: .t),
                    gain: try container.decode(Double.self, forKey: .gain)
                )
            )
        case .setLaneMuted:
            self = .setLaneMuted(
                lane: try container.decode(AudioLane.self, forKey: .lane),
                muted: try container.decode(Bool.self, forKey: .muted)
            )
        case .setLaneOffset:
            self = .setLaneOffset(
                lane: try container.decode(AudioLane.self, forKey: .lane),
                seconds: try container.decode(TimeInterval.self, forKey: .seconds)
            )
        case .excludeWords:
            self = .excludeWords(try container.decode([ExcludedWord].self, forKey: .words))
        case .restoreWords:
            self = .restoreWords(ids: try container.decode([Int].self, forKey: .ids))
        case .setCameraStyle:
            self = .setCameraStyle(PiPStyle(
                shape: try container.decodeIfPresent(PiPStyle.Shape.self, forKey: .shape) ?? .rectangle,
                cornerRadius: try container.decodeIfPresent(Double.self, forKey: .cornerRadius) ?? 0,
                borderWidth: try container.decodeIfPresent(Double.self, forKey: .borderWidth) ?? 0,
                borderColor: try container.decodeIfPresent([Double].self, forKey: .borderColor) ?? [1, 1, 1],
                shadowOpacity: try container.decodeIfPresent(Double.self, forKey: .shadowOpacity) ?? 0,
                shadowRadius: try container.decodeIfPresent(Double.self, forKey: .shadowRadius) ?? 0
            ))
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        switch self {
        case .removeRange(let span):
            try container.encode(Op.removeRange, forKey: .op)
            try container.encode(span.start, forKey: .start)
            try container.encode(span.end, forKey: .end)
        case .splitClip(let t):
            try container.encode(Op.splitClip, forKey: .op)
            try container.encode(t, forKey: .t)
        case .setOverlayKeyframe(let keyframe):
            try container.encode(Op.setOverlayKeyframe, forKey: .op)
            try container.encode(keyframe.t, forKey: .t)
            try container.encode(keyframe.rect, forKey: .rect)
            try container.encode(keyframe.visible, forKey: .visible)
        case .removeOverlayKeyframe(let t):
            try container.encode(Op.removeOverlayKeyframe, forKey: .op)
            try container.encode(t, forKey: .t)
        case .setLaneGain(let lane, let keyframe):
            try container.encode(Op.setLaneGain, forKey: .op)
            try container.encode(lane, forKey: .lane)
            try container.encode(keyframe.t, forKey: .t)
            try container.encode(keyframe.gain, forKey: .gain)
        case .setLaneMuted(let lane, let muted):
            try container.encode(Op.setLaneMuted, forKey: .op)
            try container.encode(lane, forKey: .lane)
            try container.encode(muted, forKey: .muted)
        case .setLaneOffset(let lane, let seconds):
            try container.encode(Op.setLaneOffset, forKey: .op)
            try container.encode(lane, forKey: .lane)
            try container.encode(seconds, forKey: .seconds)
        case .excludeWords(let words):
            try container.encode(Op.excludeWords, forKey: .op)
            try container.encode(words, forKey: .words)
        case .restoreWords(let ids):
            try container.encode(Op.restoreWords, forKey: .op)
            try container.encode(ids, forKey: .ids)
        case .setCameraStyle(let style):
            try container.encode(Op.setCameraStyle, forKey: .op)
            try container.encode(style.shape, forKey: .shape)
            try container.encode(style.cornerRadius, forKey: .cornerRadius)
            try container.encode(style.borderWidth, forKey: .borderWidth)
            try container.encode(style.borderColor, forKey: .borderColor)
            try container.encode(style.shadowOpacity, forKey: .shadowOpacity)
            try container.encode(style.shadowRadius, forKey: .shadowRadius)
        }
    }
}

/// Operations are rejected rather than clamped, so a bad agent suggestion surfaces as an
/// error the user can see instead of a silently mangled edit.
enum EditOperationError: Error, Equatable, LocalizedError {
    case timeNotFinite
    case emptyRange
    case timeOutsideTimeline(TimeInterval)
    case wouldRemoveEntireTimeline
    case noSplitPointInsideAClip(TimeInterval)
    case invalidRect
    case noOverlayKeyframe(at: TimeInterval)
    case wouldRemoveLastOverlayKeyframe
    case gainOutOfRange(Double)
    case offsetOutOfRange(TimeInterval)
    case noWordsGiven
    case wouldRemoveEntireTimeline_words
    case invalidCameraStyle

    var errorDescription: String? {
        switch self {
        case .timeNotFinite:
            return "The edit referred to a time that isn't a real number."
        case .emptyRange:
            return "The range to remove is empty."
        case .timeOutsideTimeline(let t):
            return String(format: "%.2fs is outside the recording.", t)
        case .wouldRemoveEntireTimeline:
            return "That would remove the entire recording."
        case .noSplitPointInsideAClip(let t):
            return String(format: "There is nothing to split at %.2fs.", t)
        case .invalidRect:
            return "The camera overlay rectangle is not a valid size."
        case .noOverlayKeyframe(let t):
            return String(format: "There is no camera keyframe at %.2fs.", t)
        case .wouldRemoveLastOverlayKeyframe:
            return "The camera needs at least one keyframe."
        case .gainOutOfRange(let gain):
            return String(format: "Gain %.2f is outside 0-1.", gain)
        case .offsetOutOfRange(let seconds):
            return String(format: "An audio slip of %.2fs is outside the +/-5s limit.", seconds)
        case .noWordsGiven:
            return "No words were given to change."
        case .wouldRemoveEntireTimeline_words:
            return "Cutting those words would leave nothing behind."
        case .invalidCameraStyle:
            return "That camera style has values outside the allowed range."
        }
    }
}

extension SessionEdit {
    /// Pure. Returns the document the operation produces, or throws without touching it.
    func applying(_ operation: EditOperation) throws -> SessionEdit {
        var edit = self
        switch operation {
        case .removeRange(let span):
            edit.clips = try Self.removing(span, from: clips)
        case .splitClip(let t):
            edit.clips = try Self.splitting(clips, at: try Self.snapped(t))
        case .setOverlayKeyframe(let keyframe):
            guard keyframe.rect.isValid else { throw EditOperationError.invalidRect }
            var updated = keyframe
            updated.t = try Self.snapped(keyframe.t)
            edit.cameraOverlay = Self.upserting(updated, into: cameraOverlay)
        case .removeOverlayKeyframe(let t):
            let time = try Self.snapped(t)
            // Nearest within a frame, rather than an exact float match. The agent works from
            // a rounded digest, so it will ask to remove "84.5" for a keyframe stored at
            // 84.5001 — and demanding exactness made those keyframes unremovable.
            guard let target = cameraOverlay
                .filter({ abs($0.t - time) <= Self.keyframeTolerance })
                .min(by: { abs($0.t - time) < abs($1.t - time) })
            else { throw EditOperationError.noOverlayKeyframe(at: time) }
            guard cameraOverlay.count > 1 else {
                throw EditOperationError.wouldRemoveLastOverlayKeyframe
            }
            edit.cameraOverlay = cameraOverlay.filter { $0.t != target.t }
        case .setLaneGain(let lane, let keyframe):
            guard keyframe.gain.isFinite, (0...1).contains(keyframe.gain) else {
                throw EditOperationError.gainOutOfRange(keyframe.gain)
            }
            let time = try Self.snapped(keyframe.t)
            edit.audioLanes = try Self.updatingLane(lane, in: audioLanes) { settings in
                settings.gain = Self.upserting(GainKeyframe(t: time, gain: keyframe.gain), into: settings.gain)
            }
        case .setLaneMuted(let lane, let muted):
            edit.audioLanes = try Self.updatingLane(lane, in: audioLanes) { $0.muted = muted }
        case .setLaneOffset(let lane, let seconds):
            guard seconds.isFinite, abs(seconds) <= Self.maximumLaneOffset else {
                throw EditOperationError.offsetOutOfRange(seconds)
            }
            edit.audioLanes = try Self.updatingLane(lane, in: audioLanes) { $0.offset = seconds }

        case .excludeWords(let words):
            let usable = words.filter { $0.end > $0.start && $0.start.isFinite && $0.end.isFinite }
            guard !usable.isEmpty else { throw EditOperationError.noWordsGiven }

            let existing = Set(excludedWords.map(\.id))
            edit.excludedWords = (excludedWords + usable.filter { !existing.contains($0.id) })
                .sorted { $0.start < $1.start }
            guard edit.effectiveClips.contains(where: { !$0.source.isEmpty }) else {
                throw EditOperationError.wouldRemoveEntireTimeline_words
            }

        case .restoreWords(let ids):
            guard !ids.isEmpty else { throw EditOperationError.noWordsGiven }
            let wanted = Set(ids)
            edit.excludedWords = excludedWords.filter { !wanted.contains($0.id) }

        case .setCameraStyle(let style):
            guard style.isValid else { throw EditOperationError.invalidCameraStyle }
            edit.cameraStyle = style
        }
        return edit
    }

    /// A slip beyond this is a sign something is wrong rather than a sync nudge.
    static let maximumLaneOffset: TimeInterval = 5

    /// One frame at 30fps. Overlay keyframes closer together than this are the same keyframe:
    /// nothing needs two camera positions inside a single frame, and allowing it produced
    /// pairs the agent could not address.
    static let keyframeTolerance: TimeInterval = 1.0 / 30.0

    /// Snaps to `Timeline.timescale` so that a time authored by the UI, by an agent, or read
    /// back from `edit.json` all land on the same tick and compare equal.
    private static func snapped(_ t: TimeInterval) throws -> TimeInterval {
        guard t.isFinite, t >= 0 else { throw EditOperationError.timeNotFinite }
        return Timeline.seconds(Timeline.time(seconds: t))
    }

    private static func removing(_ span: TimeSpan, from clips: [TimelineClip]) throws -> [TimelineClip] {
        let start = try snapped(span.start)
        let end = try snapped(span.end)
        guard end > start else { throw EditOperationError.emptyRange }

        // Rejected rather than treated as a no-op: a range that touches nothing means the
        // caller (or the agent) was working from a stale view of the timeline.
        guard clips.contains(where: { start < $0.source.end && end > $0.source.start }) else {
            throw EditOperationError.timeOutsideTimeline(start)
        }

        let survivors: [TimelineClip] = clips.flatMap { clip -> [TimelineClip] in
            let source = clip.source
            guard start < source.end, end > source.start else { return [clip] }

            var pieces: [TimelineClip] = []
            if start > source.start {
                pieces.append(TimelineClip(id: clip.id, source: TimeSpan(start: source.start, end: start)))
            }
            if end < source.end {
                let id = pieces.isEmpty ? clip.id : UUID()
                pieces.append(TimelineClip(id: id, source: TimeSpan(start: end, end: source.end)))
            }
            return pieces
        }

        guard survivors.contains(where: { !$0.source.isEmpty }) else {
            throw EditOperationError.wouldRemoveEntireTimeline
        }
        return survivors
    }

    private static func splitting(_ clips: [TimelineClip], at t: TimeInterval) throws -> [TimelineClip] {
        // Strictly inside: splitting at a clip's own boundary is already-split, not an edit.
        guard clips.contains(where: { $0.source.start < t && t < $0.source.end }) else {
            throw EditOperationError.noSplitPointInsideAClip(t)
        }

        return clips.flatMap { clip -> [TimelineClip] in
            guard clip.source.start < t, t < clip.source.end else { return [clip] }
            return [
                TimelineClip(id: clip.id, source: TimeSpan(start: clip.source.start, end: t)),
                TimelineClip(source: TimeSpan(start: t, end: clip.source.end))
            ]
        }
    }

    /// Replaces any keyframe within a frame of the new one, rather than only an exact time
    /// match. Two drags at almost the same playhead used to leave a near-duplicate pair that
    /// rounded to the same displayed time and could not then be told apart.
    ///
    /// The existing keyframe's time is kept and only its contents updated, so that repeatedly
    /// nudging the camera at roughly the same spot doesn't make the keyframe creep along the
    /// timeline — and a time the agent was told about stays valid afterwards.
    private static func upserting(_ keyframe: OverlayKeyframe, into keyframes: [OverlayKeyframe]) -> [OverlayKeyframe] {
        let nearby = keyframes.filter { abs($0.t - keyframe.t) <= Self.keyframeTolerance }
        var updated = keyframe
        if let earliest = nearby.map(\.t).min() {
            updated.t = earliest
        }

        return (keyframes.filter { abs($0.t - keyframe.t) > Self.keyframeTolerance } + [updated])
            .sorted { $0.t < $1.t }
    }

    private static func upserting(_ keyframe: GainKeyframe, into keyframes: [GainKeyframe]) -> [GainKeyframe] {
        (keyframes.filter { $0.t != keyframe.t } + [keyframe]).sorted { $0.t < $1.t }
    }

    private static func updatingLane(
        _ lane: AudioLane,
        in lanes: [AudioLaneSettings],
        _ mutate: (inout AudioLaneSettings) -> Void
    ) throws -> [AudioLaneSettings] {
        var lanes = lanes
        if !lanes.contains(where: { $0.lane == lane }) {
            lanes.append(AudioLaneSettings(lane: lane))
        }
        for index in lanes.indices where lanes[index].lane == lane {
            mutate(&lanes[index])
        }
        return lanes
    }
}
