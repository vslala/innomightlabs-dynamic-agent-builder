import CoreMedia
import Foundation

/// Builds a `ReviewProjection`. Pure, and the only clock authority in the program.
///
/// Takes the **resolved timeline**, not the probes. Taking probes would force this to
/// recompute `probe.alignmentCorrection + document.offset(for: lane)` — which is exactly the
/// duplicated conversion this whole design exists to eliminate, reintroduced by the change
/// meant to remove it.
enum ReviewProjector {
    static func project(
        timeline: ResolvedTimeline,
        document: SessionEdit,
        transcript: Transcript?,
        events: EventTimeline
    ) -> ReviewProjection {
        let laneOffsets = Dictionary(
            timeline.audio.map { ($0.lane, Timeline.seconds($0.timeOffset)) },
            uniquingKeysWith: { first, _ in first }
        )
        // The transcript is stamped in the microphone file's clock, so the conversion to
        // source time is that lane's total offset — automatic correction plus manual slip.
        // Read from the resolved lane rather than the document's stored value, which can go
        // stale.
        let micOffset = laneOffsets[.microphone] ?? document.micTimeOffset

        let recording = StampSpan<Source>(start: 0, end: max(0, document.recordingDuration))
        let segments = timeline.timeMap.segments

        let regions = self.regions(document: document, recording: recording)
        let words = self.words(
            transcript: transcript,
            micOffset: micOffset,
            segments: segments
        )

        return ReviewProjection(
            timeline: timeline,
            recording: recording,
            edited: StampSpan(start: 0, end: Timeline.seconds(timeline.duration)),
            regions: regions,
            words: words,
            cues: cues(transcript: transcript, words: words),
            markers: markers(document: document, events: events, segments: segments),
            splits: document.splitPoints.sorted().map(Stamp.init),
            micOffset: micOffset,
            laneOffsets: laneOffsets
        )
    }

    // MARK: - Regions

    /// Kept and cut stretches tiling the whole recording, in order.
    ///
    /// Built from the merged cut ranges so the regions are disjoint, but each cut region keeps
    /// the ids of *every* document cut it covers — a word cut inside a range cut contributes
    /// both, and restoring the region must remove both.
    private static func regions(
        document: SessionEdit,
        recording: StampSpan<Source>
    ) -> [ProjectedRegion] {
        guard recording.duration > 0 else { return [] }

        let merged = SessionEdit.mergedCutRanges(
            document.cuts,
            recordingDuration: document.recordingDuration
        )

        var result: [ProjectedRegion] = []
        var cursor = 0.0

        for range in merged {
            let span = StampSpan<Source>(
                start: Timeline.seconds(range.start),
                end: Timeline.seconds(range.end)
            )
            if span.start.seconds > cursor {
                let kept = StampSpan<Source>(start: cursor, end: span.start.seconds)
                result.append(ProjectedRegion(
                    id: Self.stableID(kept),
                    span: kept,
                    kind: .kept,
                    cutIDs: []
                ))
            }

            let covering = document.cuts.filter { cut in
                cut.span.start < span.end.seconds && cut.span.end > span.start.seconds
            }
            result.append(ProjectedRegion(
                // Derived from the span rather than fresh, so an unchanged document yields an
                // equal projection and SwiftUI's `.equatable()` short-circuits hold.
                id: Self.stableID(span),
                span: span,
                kind: .cut(origins: covering.map(\.origin)),
                cutIDs: covering.map(\.id)
            ))
            cursor = max(cursor, span.end.seconds)
        }

        if cursor < recording.end.seconds {
            result.append(ProjectedRegion(
                id: Self.stableID(StampSpan(start: cursor, end: recording.end.seconds)),
                span: StampSpan(start: cursor, end: recording.end.seconds),
                kind: .kept,
                cutIDs: []
            ))
        }

        return result
    }

    /// Deterministic from the span, so identical documents project equal regions — which is
    /// what keeps `.equatable()` able to short-circuit the waveform's rasterisation. A fresh
    /// `UUID()` here silently made every projection unequal and re-rasterised on every publish.
    ///
    private static func stableID(_ span: StampSpan<Source>) -> UUID {
        var bytes = [UInt8](repeating: 0, count: 16)
        withUnsafeBytes(of: span.start.cm.value.littleEndian) { raw in
            for index in 0..<8 { bytes[index] = raw[index] }
        }
        withUnsafeBytes(of: span.end.cm.value.littleEndian) { raw in
            for index in 0..<8 { bytes[8 + index] = raw[index] }
        }
        return UUID(uuid: (
            bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
            bytes[8], bytes[9], bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]
        ))
    }

    // MARK: - Words

    /// Places every transcript word on both clocks in a single pass.
    ///
    /// A merge join rather than a `compositionSpans(forSource:)` call per word: words are
    /// sorted by start and the derived segments are source-monotonic, so this is
    /// `words + segments` steps instead of `words × segments` intersections with an allocation
    /// each — microseconds instead of tens of milliseconds on a real document.
    private static func words(
        transcript: Transcript?,
        micOffset: TimeInterval,
        segments: [TimeMap.Segment]
    ) -> [ProjectedWord] {
        guard let transcript else { return [] }

        let sourceWords = transcript.allWords
            .map { word -> (word: Transcript.Word, span: StampSpan<Source>) in
                (word, StampSpan(start: word.start + micOffset, end: word.end + micOffset))
            }
            .sorted { $0.span.start < $1.span.start }

        var result: [ProjectedWord] = []
        result.reserveCapacity(sourceWords.count)
        var segmentIndex = 0

        for entry in sourceWords {
            // Advance past segments that end before this word starts. Never rewound, which is
            // what makes the whole pass linear.
            while segmentIndex < segments.count,
                  Timeline.seconds(segments[segmentIndex].source.end) <= entry.span.start.seconds {
                segmentIndex += 1
            }

            var spans: [StampSpan<Composition>] = []
            var lookahead = segmentIndex
            while lookahead < segments.count {
                let segment = segments[lookahead]
                let sourceStart = Timeline.seconds(segment.source.start)
                if sourceStart >= entry.span.end.seconds { break }

                let overlapStart = max(sourceStart, entry.span.start.seconds)
                let overlapEnd = min(Timeline.seconds(segment.source.end), entry.span.end.seconds)
                if overlapEnd > overlapStart {
                    let compositionStart = Timeline.seconds(segment.composition.start)
                        + (overlapStart - sourceStart)
                    spans.append(StampSpan(
                        start: compositionStart,
                        end: compositionStart + (overlapEnd - overlapStart)
                    ))
                }
                lookahead += 1
            }

            result.append(ProjectedWord(
                id: entry.word.id,
                text: entry.word.text,
                cueID: cueID(of: entry.word.id, in: transcript),
                source: entry.span,
                composition: spans
            ))
        }

        return result
    }

    private static func cueID(of wordID: Int, in transcript: Transcript) -> Int {
        for segment in transcript.segments where segment.words.contains(where: { $0.id == wordID }) {
            return segment.id
        }
        return -1
    }

    /// Cues, assembled from their already-placed words so the two can never disagree.
    private static func cues(transcript: Transcript?, words: [ProjectedWord]) -> [ProjectedCue] {
        guard let transcript else { return [] }
        let byCue = Dictionary(grouping: words, by: \.cueID)

        return transcript.segments.compactMap { segment -> ProjectedCue? in
            let cueWords = (byCue[segment.id] ?? []).sorted { $0.source.start < $1.source.start }
            guard let first = cueWords.first, let last = cueWords.last else { return nil }

            return ProjectedCue(
                id: segment.id,
                text: segment.text,
                source: StampSpan(start: first.source.start, end: last.source.end),
                // Merged from the words, so a cue straddling a cut reports both halves.
                composition: merged(cueWords.flatMap(\.composition)),
                wordIDs: cueWords.map(\.id)
            )
        }
    }

    private static func merged(_ spans: [StampSpan<Composition>]) -> [StampSpan<Composition>] {
        let sorted = spans.sorted { $0.start < $1.start }
        var result: [StampSpan<Composition>] = []
        for span in sorted where !span.isEmpty {
            if let last = result.last, span.start <= last.end {
                result[result.count - 1] = StampSpan(start: last.start, end: max(last.end, span.end))
            } else {
                result.append(span)
            }
        }
        return result
    }

    // MARK: - Markers

    /// Both marker systems, tagged so the UI can tell a fact from an editorial choice.
    private static func markers(
        document: SessionEdit,
        events: EventTimeline,
        segments: [TimeMap.Segment]
    ) -> [ProjectedMarker] {
        let recording = events.markers.map { entry in
            ProjectedMarker(
                id: "recording-\(entry.mediaTs)",
                label: entry.event.label ?? "Marker",
                kind: .recording,
                source: Stamp(entry.mediaTs),
                composition: composition(forSource: entry.mediaTs, segments: segments)
            )
        }

        let editorial = document.markers.map { marker in
            ProjectedMarker(
                id: marker.id.uuidString,
                label: marker.label,
                kind: .editorial(id: marker.id),
                source: Stamp(marker.at),
                composition: composition(forSource: marker.at, segments: segments)
            )
        }

        return (recording + editorial).sorted { $0.source < $1.source }
    }

    private static func composition(
        forSource time: TimeInterval,
        segments: [TimeMap.Segment]
    ) -> Stamp<Composition>? {
        for segment in segments {
            let start = Timeline.seconds(segment.source.start)
            let end = Timeline.seconds(segment.source.end)
            if time >= start && time < end {
                return Stamp(Timeline.seconds(segment.composition.start) + (time - start))
            }
        }
        // Sits inside a cut, or past the end: clamp to the end of the last segment that
        // precedes it, so a marker made moments before Stop is still reachable.
        if let last = segments.last(where: { Timeline.seconds($0.source.end) <= time }) {
            return Stamp(Timeline.seconds(last.composition.end))
        }
        return nil
    }
}
