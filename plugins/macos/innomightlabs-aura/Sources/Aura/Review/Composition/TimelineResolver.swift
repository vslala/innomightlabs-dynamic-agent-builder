import CoreMedia
import Foundation

/// Turns a `SessionEdit` plus the probed source files into a `ResolvedTimeline`.
///
/// Pure, and the only place that decides render size, layer identity, and where keyframes
/// land on the composition timeline. See `ResolvedTimeline` for why that concentration
/// matters.
enum TimelineResolver {
    /// Used when a session has no usable video at all, so the composition still has a legal
    /// render size rather than a zero one.
    static let fallbackRenderSize = CGSize(width: 1280, height: 720)

    /// - Parameter speechClips: the rendered clip for each replacement that has one. Passed in
    ///   so this stays pure; a replacement missing from it plays as the original voice.
    static func resolve(
        document: SessionEdit,
        probes: [SourceTrackProbe],
        style: PiPStyle? = nil,
        speechClips: [UUID: URL] = [:],
        cursorPath: CursorPath? = nil,
        narrationClips: [UUID: URL] = [:]
    ) -> ResolvedTimeline {
        // The document owns the style; the parameter is an override for previews and tests.
        let style = style ?? document.cameraStyle
        // Grouped rather than a one-probe-per-kind dictionary: a track a live profile switch
        // turned off and back on probes as several segments of the same kind, ascending —
        // `SourceTrackProbe.probeAll` already returns them in that order.
        let byKind = Dictionary(grouping: probes, by: \.kind)
        let timeMap = document.timeMap

        // Normally screen is the base and camera the overlay. But `ScreenCaptureSource`
        // forwards only complete frames and sets no maximum frame interval, so recording a
        // static screen can yield a screen track with no frames at all — in which case the
        // camera is promoted to full frame rather than floating over black.
        let screenSegments = byKind[.screen]
        let cameraSegments = byKind[.camera]
        let baseSegments = screenSegments ?? cameraSegments
        let overlaySegments = screenSegments != nil ? cameraSegments : nil

        // A crop never applies to a camera promoted to the base layer.
        let screenCrop = screenSegments == nil ? nil : document.screenCrop
        let renderSize = renderSize(for: baseSegments?.first, crop: screenCrop)
        let overlayKeyframes = resolveOverlay(document: document, timeMap: timeMap)
        let speech = document.speechReplacements.compactMap { replacement in
            speechClips[replacement.id].map {
                ResolvedSpeechReplacement(
                    id: replacement.id,
                    url: $0,
                    span: replacement.span,
                    duration: Timeline.time(seconds: replacement.duration)
                )
            }
        }
        // Where the original voice must be silent: wherever new speech plays over it.
        let replacedRanges = speech.flatMap { timeMap.compositionRanges(forSource: $0.span.cmRange) }
        let voiceKeyframes = resolveGain(document: document, lane: .microphone, timeMap: timeMap)
        // Effects draw on the screen picture, so a camera promoted to the base has none.
        let cursor = document.cursorStyle.visible ? cursorPath.flatMap { $0.isEmpty ? nil : $0 } : nil
        let effects = screenSegments == nil || (document.zooms.isEmpty && cursor == nil)
            ? nil
            : ResolvedDemoEffects(zooms: document.zooms, cursor: cursor, cursorStyle: document.cursorStyle, timeMap: timeMap)
        let narration = document.narration.compactMap { line in
            narrationClips[line.id].map {
                ResolvedNarration(id: line.id, url: $0, at: line.at, duration: Timeline.time(seconds: line.duration))
            }
        }

        return ResolvedTimeline(
            timeMap: timeMap,
            renderSize: renderSize,
            frameDuration: Timeline.frameDuration,
            base: baseSegments.map {
                // The base layer fills the frame; it has no keyframes of its own.
                ResolvedVideoLayer(
                    segments: Self.placeSegments($0),
                    keyframes: [ResolvedOverlayKeyframe(
                        at: .zero,
                        rect: NormalizedRect(x: 0, y: 0, width: 1, height: 1),
                        visible: true
                    )]
                )
            },
            overlay: overlaySegments.map {
                ResolvedVideoLayer(segments: Self.placeSegments($0), keyframes: overlayKeyframes)
            },
            audio: AudioLane.allCases.compactMap { lane in
                let segments = probes.filter { $0.kind.lane == lane }
                guard !segments.isEmpty else { return nil }
                // Automatic per-segment correction plus the user's one manual slip for the
                // whole lane.
                let slip = Timeline.time(seconds: document.offset(for: lane))
                let studioSound = document.settings(for: lane).studioSound
                let keyframes = lane == .microphone
                    ? silencing(voiceKeyframes, over: replacedRanges, duration: timeMap.cmDuration)
                    : resolveGain(document: document, lane: lane, timeMap: timeMap)
                return ResolvedAudioLane(
                    lane: lane,
                    segments: segments.map {
                        PlacedSegment(
                            probe: $0.playing(studioSound: studioSound),
                            timeOffset: $0.alignmentCorrection + slip
                        )
                    },
                    keyframes: keyframes
                )
            },
            style: style,
            screenCrop: screenCrop,
            speech: speech,
            speechKeyframes: voiceKeyframes,
            effects: effects,
            narration: narration
        )
    }

    /// The lane's gain with silence cut under each range, returning to whatever level was in
    /// force when the range ends.
    ///
    /// Derived rather than authored, so it never touches the document's own gain keyframes: the
    /// user's level is still theirs, and restoring the original voice needs no cleanup.
    static func silencing(
        _ keyframes: [ResolvedGainKeyframe],
        over ranges: [CMTimeRange],
        duration: CMTime
    ) -> [ResolvedGainKeyframe] {
        let merged = ranges
            .filter { $0.duration > .zero }
            .sorted { $0.start < $1.start }
            .reduce(into: [CMTimeRange]()) { result, range in
                // Touching ranges merge, or the level returning at one's end would collide with
                // the next one's silence at the same instant.
                if let last = result.last, range.start <= last.end {
                    result[result.count - 1] = CMTimeRange(start: last.start, end: max(last.end, range.end))
                } else {
                    result.append(range)
                }
            }
        guard !merged.isEmpty else { return keyframes }

        func level(at time: CMTime) -> Double {
            keyframes.last { $0.at <= time }?.gain ?? keyframes.first?.gain ?? 1
        }

        var result = keyframes.filter { keyframe in
            !merged.contains { $0.start <= keyframe.at && keyframe.at < $0.end }
        }
        for range in merged {
            result.append(ResolvedGainKeyframe(at: range.start, gain: 0))
            if range.end < duration {
                result.append(ResolvedGainKeyframe(at: range.end, gain: level(at: range.end)))
            }
        }
        return result.sorted { $0.at < $1.at }
    }

    private static func placeSegments(_ probes: [SourceTrackProbe]) -> [PlacedSegment] {
        probes.map { PlacedSegment(probe: $0, timeOffset: $0.alignmentCorrection) }
    }

    /// The base track's display size, floored to even dimensions because HEVC wants them.
    /// Read from the written file rather than `composition.naturalSize`, which is documented
    /// as the first video track's size and ignores `preferredTransform`.
    private static func renderSize(for probe: SourceTrackProbe?, crop: NormalizedRect?) -> CGSize {
        guard let size = probe?.displaySize, size.width >= 2, size.height >= 2 else {
            return fallbackRenderSize
        }
        let even = { (value: CGFloat) in max(2, (value / 2).rounded(.down) * 2) }
        let cropped = crop?.scaled(to: size).size ?? size
        return CGSize(width: even(cropped.width), height: even(cropped.height))
    }

    private static func resolveOverlay(document: SessionEdit, timeMap: TimeMap) -> [ResolvedOverlayKeyframe] {
        let sorted = document.cameraOverlay.sorted { $0.t < $1.t }
        let fallback = OverlayKeyframe(t: 0, rect: .defaultCameraOverlay, visible: true)

        let resolved = mapToComposition(
            sourceKeyframes: sorted,
            time: \.t,
            timeMap: timeMap,
            stateAt: { document.overlay(at: $0) ?? fallback },
            make: { at, keyframe in
                ResolvedOverlayKeyframe(at: at, rect: keyframe.rect, visible: keyframe.visible)
            },
            isRedundant: { $0.rect == $1.rect && $0.visible == $1.visible }
        )

        return resolved.isEmpty
            ? [ResolvedOverlayKeyframe(at: .zero, rect: fallback.rect, visible: fallback.visible)]
            : resolved
    }

    private static func resolveGain(
        document: SessionEdit,
        lane: AudioLane,
        timeMap: TimeMap
    ) -> [ResolvedGainKeyframe] {
        let sorted = document.settings(for: lane).gain.sorted { $0.t < $1.t }

        let resolved = mapToComposition(
            sourceKeyframes: sorted,
            time: \.t,
            timeMap: timeMap,
            stateAt: { GainKeyframe(t: $0, gain: document.gain(for: lane, at: $0)) },
            make: { at, keyframe in ResolvedGainKeyframe(at: at, gain: keyframe.gain) },
            isRedundant: { $0.gain == $1.gain }
        )

        return resolved.isEmpty
            ? [ResolvedGainKeyframe(at: .zero, gain: document.gain(for: lane, at: 0))]
            : resolved
    }

    /// Projects source-time keyframes onto the composition timeline.
    ///
    /// Each surviving segment gets an explicit keyframe at its own composition start,
    /// carrying whatever state was in force at that point in *source* time. That is what
    /// makes a cut correct in the case that is easy to miss: a keyframe authored inside a
    /// range that was later removed maps to no composition time of its own, but the state it
    /// established still governs the content that follows it — so it has to be re-emitted at
    /// the start of the next segment rather than dropped.
    private static func mapToComposition<Source, Resolved>(
        sourceKeyframes: [Source],
        time: (Source) -> TimeInterval,
        timeMap: TimeMap,
        stateAt: (TimeInterval) -> Source,
        make: (CMTime, Source) -> Resolved,
        isRedundant: (Source, Source) -> Bool
    ) -> [Resolved] {
        var resolved: [Resolved] = []
        var previous: Source?

        for segment in timeMap.segments {
            let sourceStart = Timeline.seconds(segment.source.start)
            let sourceEnd = Timeline.seconds(segment.source.end)

            let atSegmentStart = stateAt(sourceStart)
            if previous.map({ !isRedundant($0, atSegmentStart) }) ?? true {
                resolved.append(make(segment.composition.start, atSegmentStart))
            }
            previous = atSegmentStart

            for keyframe in sourceKeyframes where time(keyframe) > sourceStart && time(keyframe) < sourceEnd {
                if let previous, isRedundant(previous, keyframe) { continue }
                let offset = Timeline.time(seconds: time(keyframe)) - segment.source.start
                resolved.append(make(segment.composition.start + offset, keyframe))
                previous = keyframe
            }
        }

        return resolved
    }
}
