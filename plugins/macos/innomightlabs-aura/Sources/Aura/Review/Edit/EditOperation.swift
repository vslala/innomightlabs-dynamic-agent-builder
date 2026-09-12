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
    /// Restore specific cuts by id — what clicking a shaded region on the waveform does.
    case uncut(ids: [UUID])
    /// Remove an edit boundary previously added by `splitClip`.
    case removeSplit(at: TimeInterval)
    case addMarker(EditMarker)
    case removeMarker(id: UUID)
    case renameMarker(id: UUID, label: String)
    case moveMarker(id: UUID, to: TimeInterval)
    case rename(String)
    /// Removes several spans as ONE operation.
    ///
    /// Exists so a bulk action — remove silences, a filler sweep — is a single undo step.
    /// Applying N single cuts would put N entries on the stack, and a user who asks to remove
    /// silences expects one Cmd+Z to bring them all back.
    case removeRanges([TimeSpan])

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
        case uncut
        case removeSplit = "remove_split"
        case addMarker = "add_marker"
        case removeMarker = "remove_marker"
        case renameMarker = "rename_marker"
        case moveMarker = "move_marker"
        case rename
        case removeRanges = "remove_ranges"
    }

    private enum CodingKeys: String, CodingKey {
        case op, start, end, t, rect, visible, lane, gain, muted, seconds, words, ids
        case shape, cornerRadius, borderWidth, borderColor, shadowOpacity, shadowRadius
        case cutIds, id, label, name, spans
        // Accepted on decode only, never written: a language model reaches for these names
        // regardless of what we document, and losing a whole operation to a synonym is worse
        // than accepting one.
        case at, to
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
        case .uncut:
            self = .uncut(ids: try container.decodeIfPresent([UUID].self, forKey: .cutIds)
                ?? container.decode([UUID].self, forKey: .ids))
        case .removeSplit:
            self = .removeSplit(at: try container.decode(TimeInterval.self, forKey: .t))
        case .addMarker:
            self = .addMarker(EditMarker(
                at: try container.decodeIfPresent(TimeInterval.self, forKey: .t)
                    ?? container.decode(TimeInterval.self, forKey: .at),
                label: try container.decodeIfPresent(String.self, forKey: .label) ?? ""
            ))
        case .removeMarker:
            self = .removeMarker(id: try container.decode(UUID.self, forKey: .id))
        case .renameMarker:
            self = .renameMarker(
                id: try container.decode(UUID.self, forKey: .id),
                label: try container.decode(String.self, forKey: .label)
            )
        case .moveMarker:
            self = .moveMarker(
                id: try container.decode(UUID.self, forKey: .id),
                to: try container.decodeIfPresent(TimeInterval.self, forKey: .t)
                    ?? container.decodeIfPresent(TimeInterval.self, forKey: .to)
                    ?? container.decode(TimeInterval.self, forKey: .at)
            )
        case .rename:
            self = .rename(try container.decode(String.self, forKey: .name))
        case .removeRanges:
            self = .removeRanges(try container.decode([TimeSpan].self, forKey: .spans))
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
        case .uncut(let ids):
            try container.encode(Op.uncut, forKey: .op)
            try container.encode(ids, forKey: .cutIds)
        case .removeSplit(let t):
            try container.encode(Op.removeSplit, forKey: .op)
            try container.encode(t, forKey: .t)
        case .addMarker(let marker):
            try container.encode(Op.addMarker, forKey: .op)
            try container.encode(marker.at, forKey: .t)
            try container.encode(marker.label, forKey: .label)
        case .removeMarker(let id):
            try container.encode(Op.removeMarker, forKey: .op)
            try container.encode(id, forKey: .id)
        case .renameMarker(let id, let label):
            try container.encode(Op.renameMarker, forKey: .op)
            try container.encode(id, forKey: .id)
            try container.encode(label, forKey: .label)
        case .moveMarker(let id, let time):
            try container.encode(Op.moveMarker, forKey: .op)
            try container.encode(id, forKey: .id)
            try container.encode(time, forKey: .t)
        case .rename(let name):
            try container.encode(Op.rename, forKey: .op)
            try container.encode(name, forKey: .name)
        case .removeRanges(let spans):
            try container.encode(Op.removeRanges, forKey: .op)
            try container.encode(spans, forKey: .spans)
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
    case invalidCameraStyle
    case noCutsGiven
    case noSuchCut
    case noSuchMarker
    case alreadySplit(TimeInterval)
    case noSplit(at: TimeInterval)

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
        case .invalidCameraStyle:
            return "That camera style has values outside the allowed range."
        case .noCutsGiven:
            return "No cuts were given to restore."
        case .noSuchCut:
            return "That cut is no longer there."
        case .noSuchMarker:
            return "That marker is no longer there."
        case .alreadySplit(let t):
            return String(format: "There is already a split at %.2fs.", t)
        case .noSplit(let t):
            return String(format: "There is no split at %.2fs.", t)
        }
    }
}

extension SessionEdit {
    /// A slip beyond this is a sign something is wrong rather than a sync nudge.
    static let maximumLaneOffset: TimeInterval = 5

    /// One frame at 30fps. Overlay keyframes closer together than this are the same keyframe:
    /// nothing needs two camera positions inside a single frame, and allowing it produced
    /// pairs the agent could not address.
    static let keyframeTolerance: TimeInterval = 1.0 / 30.0

    /// Pure. Returns the document the operation produces, or throws without touching it.
    func applying(_ operation: EditOperation) throws -> SessionEdit {
        var edit = self
        switch operation {
        case .removeRange(let span):
            edit.cuts = try appendingCut(span: span, origin: .range)

        case .splitClip(let t):
            let time = try Self.snapped(t)
            // Strictly inside a surviving clip: splitting at the recording's edge, or inside
            // something already cut, is not an edit.
            guard clips.contains(where: { $0.source.start < time && time < $0.source.end }) else {
                throw EditOperationError.noSplitPointInsideAClip(time)
            }
            guard !splitPoints.contains(where: { abs($0 - time) <= Self.keyframeTolerance }) else {
                throw EditOperationError.alreadySplit(time)
            }
            edit.splitPoints = (splitPoints + [time]).sorted()

        case .removeSplit(let t):
            let time = try Self.snapped(t)
            guard let existing = splitPoints
                .filter({ abs($0 - time) <= Self.keyframeTolerance })
                .min(by: { abs($0 - time) < abs($1 - time) })
            else { throw EditOperationError.noSplit(at: time) }
            edit.splitPoints = splitPoints.filter { $0 != existing }

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
            edit.audioLanes = Self.updatingLane(lane, in: audioLanes) { settings in
                settings.gain = Self.upserting(GainKeyframe(t: time, gain: keyframe.gain), into: settings.gain)
            }

        case .setLaneMuted(let lane, let muted):
            edit.audioLanes = Self.updatingLane(lane, in: audioLanes) { $0.muted = muted }

        case .setLaneOffset(let lane, let seconds):
            guard seconds.isFinite, abs(seconds) <= Self.maximumLaneOffset else {
                throw EditOperationError.offsetOutOfRange(seconds)
            }
            edit.audioLanes = Self.updatingLane(lane, in: audioLanes) { $0.offset = seconds }

        case .excludeWords(let words):
            let usable = words.filter { $0.end > $0.start && $0.start.isFinite && $0.end.isFinite }
            guard !usable.isEmpty else { throw EditOperationError.noWordsGiven }

            let already = Set(cuts.compactMap(\.wordID))
            let added = usable
                .filter { !already.contains($0.id) }
                .map { Cut(
                    span: TimeSpan(start: $0.start, end: $0.end),
                    origin: .word(id: $0.id, text: $0.text)
                ) }
            guard !added.isEmpty else { return edit }
            edit.cuts = try Self.validated(cuts + added, recordingDuration: recordingDuration)

        case .restoreWords(let ids):
            guard !ids.isEmpty else { throw EditOperationError.noWordsGiven }
            let wanted = Set(ids)
            edit.cuts = cuts.filter { cut in cut.wordID.map { !wanted.contains($0) } ?? true }

        case .uncut(let ids):
            guard !ids.isEmpty else { throw EditOperationError.noCutsGiven }
            let wanted = Set(ids)
            guard cuts.contains(where: { wanted.contains($0.id) }) else {
                throw EditOperationError.noSuchCut
            }
            edit.cuts = cuts.filter { !wanted.contains($0.id) }

        case .addMarker(let marker):
            let at = try Self.snapped(marker.at)
            guard at <= recordingDuration else { throw EditOperationError.timeOutsideTimeline(at) }
            var updated = marker
            updated.at = at
            edit.markers = (markers + [updated]).sorted { $0.at < $1.at }

        case .removeMarker(let id):
            guard markers.contains(where: { $0.id == id }) else { throw EditOperationError.noSuchMarker }
            edit.markers = markers.filter { $0.id != id }

        case .renameMarker(let id, let label):
            guard markers.contains(where: { $0.id == id }) else { throw EditOperationError.noSuchMarker }
            edit.markers = markers.map { marker in
                guard marker.id == id else { return marker }
                var updated = marker
                updated.label = label
                return updated
            }

        case .moveMarker(let id, let time):
            let at = try Self.snapped(time)
            guard at <= recordingDuration else { throw EditOperationError.timeOutsideTimeline(at) }
            guard markers.contains(where: { $0.id == id }) else { throw EditOperationError.noSuchMarker }
            edit.markers = markers
                .map { marker -> EditMarker in
                    guard marker.id == id else { return marker }
                    var updated = marker
                    updated.at = at
                    return updated
                }
                .sorted { $0.at < $1.at }

        case .rename(let name):
            let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
            // Cleared rather than stored as "", so the UI's "has the user named this?" test
            // stays a simple nil check.
            edit.name = trimmed.isEmpty ? nil : String(trimmed.prefix(120))

        case .removeRanges(let spans):
            // Validated once over the whole set. Folding `appendingCut` would reject a span
            // that only overlaps a clip the *previous* span in this batch removed — which is
            // normal for a silence sweep, where adjacent gaps can merge.
            var appended = cuts
            for span in spans {
                let start = try Self.snapped(span.start)
                let end = try Self.snapped(span.end)
                guard end > start else { throw EditOperationError.emptyRange }
                guard start >= 0, end <= recordingDuration else {
                    throw EditOperationError.timeOutsideTimeline(start)
                }
                appended.append(Cut(span: TimeSpan(start: start, end: end), origin: .range))
            }
            guard appended.count > cuts.count else { throw EditOperationError.emptyRange }
            edit.cuts = try Self.validated(appended, recordingDuration: recordingDuration)

        case .setCameraStyle(let style):
            guard style.isValid else { throw EditOperationError.invalidCameraStyle }
            edit.cameraStyle = style
        }
        return edit
    }

    /// Adds one cut, validating the span and the result.
    ///
    /// The new cut is appended rather than merged into any it overlaps: merging would mean
    /// un-cutting it could not re-expose what was underneath, which is the whole reason cuts
    /// are stored individually.
    private func appendingCut(span: TimeSpan, origin: Cut.Origin) throws -> [Cut] {
        let start = try Self.snapped(span.start)
        let end = try Self.snapped(span.end)
        guard end > start else { throw EditOperationError.emptyRange }

        // Rejected rather than treated as a no-op: a range that touches nothing surviving
        // means the caller (or the agent) was working from a stale view of the timeline.
        guard clips.contains(where: { start < $0.source.end && end > $0.source.start }) else {
            throw EditOperationError.timeOutsideTimeline(start)
        }

        return try Self.validated(
            cuts + [Cut(span: TimeSpan(start: start, end: end), origin: origin)],
            recordingDuration: recordingDuration
        )
    }

    /// Refuses a cut set that would leave nothing to play.
    ///
    /// Without this the document on disk becomes unopenable: an empty clip list yields a zero
    /// duration, every track insert fails, and the next open lands on the error screen with no
    /// undo history to escape by.
    private static func validated(_ cuts: [Cut], recordingDuration: TimeInterval) throws -> [Cut] {
        let remaining = deriveClips(recordingDuration: recordingDuration, cuts: cuts)
        guard remaining.contains(where: { !$0.source.isEmpty }) else {
            throw EditOperationError.wouldRemoveEntireTimeline
        }
        return cuts
    }

    /// Snaps to `Timeline.timescale` so that a time authored by the UI, by an agent, or read
    /// back from `edit.json` all land on the same tick and compare equal.
    static func snapped(_ t: TimeInterval) throws -> TimeInterval {
        guard t.isFinite, t >= 0 else { throw EditOperationError.timeNotFinite }
        return Timeline.seconds(Timeline.time(seconds: t))
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
    ) -> [AudioLaneSettings] {
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
