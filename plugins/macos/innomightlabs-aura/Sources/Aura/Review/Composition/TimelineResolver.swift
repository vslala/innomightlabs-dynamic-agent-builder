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

    static func resolve(
        document: SessionEdit,
        probes: [SourceTrackProbe],
        style: PiPStyle = .plain
    ) -> ResolvedTimeline {
        let byKind = Dictionary(probes.map { ($0.kind, $0) }, uniquingKeysWith: { first, _ in first })
        let timeMap = document.timeMap

        // Normally screen is the base and camera the overlay. But `ScreenCaptureSession`
        // forwards only complete frames and sets no maximum frame interval, so recording a
        // static screen can yield a screen track with no frames at all — in which case the
        // camera is promoted to full frame rather than floating over black.
        let baseProbe = byKind[.screen] ?? byKind[.camera]
        let overlayProbe = baseProbe?.kind == .screen ? byKind[.camera] : nil

        let renderSize = renderSize(for: baseProbe)
        let overlayKeyframes = resolveOverlay(document: document, timeMap: timeMap)

        return ResolvedTimeline(
            timeMap: timeMap,
            renderSize: renderSize,
            frameDuration: Timeline.frameDuration,
            base: baseProbe.map {
                // The base layer fills the frame; it has no keyframes of its own.
                ResolvedVideoLayer(probe: $0, keyframes: [ResolvedOverlayKeyframe(
                    at: .zero,
                    rect: NormalizedRect(x: 0, y: 0, width: 1, height: 1),
                    visible: true
                )])
            },
            overlay: overlayProbe.map { ResolvedVideoLayer(probe: $0, keyframes: overlayKeyframes) },
            audio: AudioLane.allCases.compactMap { lane in
                guard let probe = probes.first(where: { $0.kind.lane == lane }) else { return nil }
                return ResolvedAudioLane(
                    lane: lane,
                    probe: probe,
                    keyframes: resolveGain(document: document, lane: lane, timeMap: timeMap)
                )
            },
            style: style
        )
    }

    /// The base track's display size, floored to even dimensions because HEVC wants them.
    /// Read from the written file rather than `composition.naturalSize`, which is documented
    /// as the first video track's size and ignores `preferredTransform`.
    private static func renderSize(for probe: SourceTrackProbe?) -> CGSize {
        guard let size = probe?.displaySize, size.width >= 2, size.height >= 2 else {
            return fallbackRenderSize
        }
        let even = { (value: CGFloat) in max(2, (value / 2).rounded(.down) * 2) }
        return CGSize(width: even(size.width), height: even(size.height))
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
