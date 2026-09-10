import CoreMedia
import Foundation

/// Maps between composition time (where the playhead is) and session/source time (where the
/// transcript, markers, and waveforms are). The two are the same only until something is cut.
///
/// Hand-rolled rather than read off `AVCompositionTrackSegment.timeMapping`, which is per
/// track — the mic's mute gaps are not the screen's — expresses source time including each
/// file's own edit-list offsets rather than the session clock, silently returns the *closest*
/// segment on a miss, and only exists on a built, non-Sendable composition.
///
/// All arithmetic is on `CMTime` at `Timeline.timescale` so boundaries compare exactly.
struct TimeMap: Equatable, Sendable {
    struct Segment: Equatable, Sendable {
        let clipID: UUID
        /// Half-open `[start, end)` on the composition timeline.
        let composition: CMTimeRange
        /// Half-open `[start, end)` on the session timeline.
        let source: CMTimeRange
    }

    let segments: [Segment]

    var cmDuration: CMTime { segments.last?.composition.end ?? .zero }
    var duration: TimeInterval { Timeline.seconds(cmDuration) }

    init(clips: [TimelineClip]) {
        var built: [Segment] = []
        var cursor = CMTime.zero

        for clip in clips {
            let source = clip.source.cmRange
            guard source.duration > .zero else { continue }
            built.append(Segment(
                clipID: clip.id,
                composition: CMTimeRange(start: cursor, duration: source.duration),
                source: source
            ))
            cursor = cursor + source.duration
        }

        segments = built
    }

    /// The source time playing at a composition time, or `nil` past the end of the timeline.
    /// Boundaries are half-open, so a time exactly on a cut belongs to the later clip.
    func sourceTime(forComposition t: CMTime) -> (clipID: UUID, source: CMTime)? {
        let time = Timeline.normalized(t)
        guard let segment = segments.first(where: {
            time >= $0.composition.start && time < $0.composition.end
        }) else { return nil }

        return (segment.clipID, segment.source.start + (time - segment.composition.start))
    }

    /// Where a source time appears on the composition timeline.
    ///
    /// Plural deliberately: duplicating a clip maps one source instant to several playhead
    /// positions, and a cut range maps to none at all. Typing this as an optional would hide
    /// both cases until trim and duplicate land.
    func compositionTimes(forSource t: CMTime) -> [CMTime] {
        let time = Timeline.normalized(t)
        return segments
            .filter { time >= $0.source.start && time < $0.source.end }
            .map { $0.composition.start + (time - $0.source.start) }
    }

    /// The composition ranges a source range survives into — empty if it was entirely cut,
    /// more than one if a cut split it.
    func compositionRanges(forSource span: CMTimeRange) -> [CMTimeRange] {
        let wanted = CMTimeRange(
            start: Timeline.normalized(span.start),
            end: Timeline.normalized(span.end)
        )
        guard wanted.duration > .zero else { return [] }

        return segments.compactMap { segment in
            let overlap = segment.source.intersection(wanted)
            guard overlap.duration > .zero else { return nil }
            return CMTimeRange(
                start: segment.composition.start + (overlap.start - segment.source.start),
                duration: overlap.duration
            )
        }
    }

    func sourceTime(forComposition t: TimeInterval) -> TimeInterval? {
        sourceTime(forComposition: Timeline.time(seconds: t)).map { Timeline.seconds($0.source) }
    }

    func compositionTimes(forSource t: TimeInterval) -> [TimeInterval] {
        compositionTimes(forSource: Timeline.time(seconds: t)).map(Timeline.seconds)
    }

    func compositionSpans(forSource span: TimeSpan) -> [TimeSpan] {
        compositionRanges(forSource: span.cmRange).map(TimeSpan.init)
    }
}
