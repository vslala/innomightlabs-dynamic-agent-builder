import CoreMedia
import Foundation

/// A stretch of the recording, either surviving or cut.
///
/// `cutIDs` is plural because two cuts can legitimately cover the same region — a word cut
/// inside a coarse range cut, which the v1 migration guarantees. Restoring a region has to
/// remove all of them, or the user clicks a shaded region, one cut disappears, and nothing
/// visibly changes.
struct ProjectedRegion: Identifiable, Equatable, Sendable {
    enum Kind: Equatable, Sendable {
        case kept
        case cut(origins: [Cut.Origin])
    }

    let id: UUID
    let span: StampSpan<Source>
    let kind: Kind
    let cutIDs: [UUID]

    var isCut: Bool {
        if case .cut = kind { return true }
        return false
    }

    /// What was removed, for labelling the region. Words are named; a plain range is not.
    var label: String? {
        guard case .cut(let origins) = kind else { return nil }
        let words = origins.compactMap { origin -> String? in
            switch origin {
            case .word(_, let text): return text
            case .filler(let word): return word
            case .range, .agent: return nil
            }
        }
        if !words.isEmpty {
            return words.count <= 3
                ? words.joined(separator: " ")
                : "\(words.prefix(3).joined(separator: " ")) +\(words.count - 3)"
        }
        if case .agent(let reason)? = origins.first, !reason.isEmpty { return reason }
        return nil
    }
}

/// One transcript word, already placed on every clock a surface needs.
struct ProjectedWord: Identifiable, Equatable, Sendable {
    let id: Int
    let text: String
    let cueID: Int
    /// Where the word is in the recording.
    let source: StampSpan<Source>
    /// Where it appears on the edited timeline — empty when it has been cut, and more than one
    /// when a cut splits it.
    let composition: [StampSpan<Composition>]

    var isCut: Bool { composition.isEmpty }
}

struct ProjectedCue: Identifiable, Equatable, Sendable {
    let id: Int
    let text: String
    let source: StampSpan<Source>
    let composition: [StampSpan<Composition>]
    let wordIDs: [Int]

    var isCut: Bool { composition.isEmpty }
}

/// A marker, distinguishing the two systems that now coexist.
struct ProjectedMarker: Identifiable, Equatable, Sendable {
    enum Kind: Equatable, Sendable {
        /// Logged during recording. An immutable fact; cannot be moved or renamed.
        case recording
        /// Placed while editing. Movable, renamable, deletable.
        case editorial(id: UUID)
    }

    let id: String
    let label: String
    let kind: Kind
    let source: Stamp<Source>
    /// Nil when the marker sits inside a cut, so nothing on the edited timeline corresponds.
    let composition: Stamp<Composition>?

    var isEditorial: Bool {
        if case .editorial = kind { return true }
        return false
    }

    var editorialID: UUID? {
        if case .editorial(let id) = kind { return id }
        return nil
    }
}

/// Everything the review surfaces read, with every clock already reconciled.
///
/// This is the **only** place in the program that converts between composition, source and
/// microphone time. Views are pure functions of it and hold no conversion logic, which is why
/// a fourth instance of the clock-confusion bug cannot be written in a view: it has nothing to
/// convert with.
///
/// Deliberately independent of the playhead, which ticks 30 times a second. Active word and
/// cue are *queries*, resolved behind change-gates in the view model rather than recomputed
/// per frame.
struct ReviewProjection: Equatable, Sendable {
    /// Held rather than copied: two time maps would be two things that can disagree.
    let timeline: ResolvedTimeline
    /// The whole recording.
    let recording: StampSpan<Source>
    /// What survives, on the edited timeline.
    let edited: StampSpan<Composition>
    /// Kept and cut stretches, in order, covering `recording` exactly.
    let regions: [ProjectedRegion]
    let words: [ProjectedWord]
    let cues: [ProjectedCue]
    let markers: [ProjectedMarker]
    /// Edit boundaries that remove nothing.
    let splits: [Stamp<Source>]
    /// Seconds to add to a microphone-file time to reach source time.
    let micOffset: TimeInterval
    /// Per-lane seconds to add to that lane's audio-file time to reach source time.
    let laneOffsets: [AudioLane: TimeInterval]

    static let empty = ReviewProjection(
        timeline: ResolvedTimeline(
            timeMap: TimeMap(clips: []),
            renderSize: TimelineResolver.fallbackRenderSize,
            frameDuration: Timeline.frameDuration,
            base: nil,
            overlay: nil,
            audio: [],
            style: .plain
        ),
        recording: StampSpan(start: 0, end: 0),
        edited: StampSpan(start: 0, end: 0),
        regions: [],
        words: [],
        cues: [],
        markers: [],
        splits: [],
        micOffset: 0,
        laneOffsets: [:]
    )

    // MARK: - Conversions

    func sourceTime(forComposition stamp: Stamp<Composition>) -> Stamp<Source>? {
        timeline.timeMap.sourceTime(forComposition: stamp.seconds).map(Stamp.init)
    }

    /// Where a source time appears on the edited timeline. Nil inside a cut.
    func compositionTime(forSource stamp: Stamp<Source>) -> Stamp<Composition>? {
        timeline.timeMap.compositionTimes(forSource: stamp.seconds).first.map(Stamp.init)
    }

    /// Composition time for a source time that may sit exactly on a cut's leading edge.
    ///
    /// `compositionTime(forSource:)` returns nothing there — ranges are half-open, so a cut's
    /// start is the *exclusive* end of the clip before it. Clicking "the start of this cut"
    /// needs the preceding segment's composition end, and having one method for it stops that
    /// off-by-one being rediscovered per caller.
    func compositionTime(atCutBoundary stamp: Stamp<Source>) -> Stamp<Composition>? {
        timeline.timeMap.compositionTime(atCutBoundary: stamp.seconds).map(Stamp.init)
    }

    /// The nearest position on the edited timeline for any source time, cut or not — what a
    /// click inside a shaded region should seek to.
    func nearestCompositionTime(forSource stamp: Stamp<Source>) -> Stamp<Composition>? {
        if let exact = compositionTime(forSource: stamp) { return exact }
        if let boundary = compositionTime(atCutBoundary: stamp) { return boundary }

        // A cut at the very start of the recording has no preceding clip to land on, so the
        // boundary lookup finds nothing and a click inside it would select the region without
        // moving the playhead at all. The first surviving moment is the honest answer.
        if let firstKept = regions.first(where: { !$0.isCut }) {
            return compositionTime(forSource: firstKept.span.start)
        }
        return nil
    }

    /// Source time -> the clock the transcript is stamped in.
    func micTime(forSource stamp: Stamp<Source>) -> Stamp<MicMedia> {
        Stamp(stamp.seconds - micOffset)
    }

    func sourceTime(forMic stamp: Stamp<MicMedia>) -> Stamp<Source> {
        Stamp(stamp.seconds + micOffset)
    }

    /// Source time -> a position in one lane's audio file, where its samples actually live.
    func audioFileTime(forSource stamp: Stamp<Source>, lane: AudioLane) -> TimeInterval {
        stamp.seconds - (laneOffsets[lane] ?? 0)
    }

    /// The inverse: where a position in a lane's audio file lands on the recording's timeline.
    ///
    /// Exists so callers never have to negate the offset themselves. That is not a
    /// hypothetical tidiness argument — the waveform drew its cached envelope shifted by
    /// twice the lane offset because the sign was written by hand at the call site.
    func sourceTime(forAudioFile seconds: TimeInterval, lane: AudioLane) -> Stamp<Source> {
        Stamp(seconds + (laneOffsets[lane] ?? 0))
    }

    // MARK: - Queries

    /// The word playing at a composition time. Binary search, since this runs per tick.
    func word(atComposition stamp: Stamp<Composition>) -> ProjectedWord? {
        guard let source = sourceTime(forComposition: stamp) else { return nil }
        return word(atSource: source)
    }

    func word(atSource stamp: Stamp<Source>) -> ProjectedWord? {
        var low = 0
        var high = words.count - 1
        while low <= high {
            let mid = (low + high) / 2
            let word = words[mid]
            if stamp < word.source.start {
                high = mid - 1
            } else if stamp >= word.source.end {
                low = mid + 1
            } else {
                return word
            }
        }
        return nil
    }

    func cue(atComposition stamp: Stamp<Composition>) -> ProjectedCue? {
        guard let word = word(atComposition: stamp) else { return nil }
        return cues.first { $0.id == word.cueID }
    }

    /// The region covering a source time. Binary search over regions, which tile `recording`.
    func region(atSource stamp: Stamp<Source>) -> ProjectedRegion? {
        var low = 0
        var high = regions.count - 1
        while low <= high {
            let mid = (low + high) / 2
            let region = regions[mid]
            if stamp < region.span.start {
                high = mid - 1
            } else if stamp >= region.span.end {
                low = mid + 1
            } else {
                return region
            }
        }
        return nil
    }

    /// Every cut overlapping a source span — what deleting or restoring a selection acts on.
    func cutIDs(overlapping span: StampSpan<Source>) -> [UUID] {
        regions
            .filter { $0.isCut && $0.span.overlaps(span) }
            .flatMap(\.cutIDs)
    }

    /// Cuts wholly inside a source span. Restoring is all-or-nothing per cut: partially
    /// un-cutting a word cut would have to degrade it to a plain range and destroy the word
    /// identity the span-repair pass depends on.
    func cutIDs(containedIn span: StampSpan<Source>) -> [UUID] {
        regions
            .filter { $0.isCut && $0.span.start >= span.start && $0.span.end <= span.end }
            .flatMap(\.cutIDs)
    }

    /// Words overlapping a source span, for cutting a selection by word rather than by range.
    func words(overlapping span: StampSpan<Source>) -> [ProjectedWord] {
        words.filter { $0.source.overlaps(span) }
    }

    /// How much of a source span actually survives — always shown alongside the span itself,
    /// because after cuts the two differ and the difference is easy to misjudge.
    func keptDuration(in span: StampSpan<Source>) -> TimeInterval {
        regions
            .filter { !$0.isCut }
            .reduce(0) { total, region in
                let start = max(region.span.start.seconds, span.start.seconds)
                let end = min(region.span.end.seconds, span.end.seconds)
                return total + max(0, end - start)
            }
    }
}
