import XCTest
import AVFoundation
@testable import Aura

/// The projection is the only clock authority in the program, so these tests are the guard on
/// every conversion the review surfaces depend on.
final class ReviewProjectionTests: XCTestCase {
    private func probe(_ kind: TrackKind, recordedOffset: TimeInterval = 0, seconds: TimeInterval = 60) -> SourceTrackProbe {
        SourceTrackProbe(
            url: URL(fileURLWithPath: "/tmp/\(kind.rawValue)"),
            kind: kind,
            duration: Timeline.time(seconds: seconds),
            displaySize: kind.isVideo ? CGSize(width: 1920, height: 1080) : nil,
            preferredTransform: .identity,
            recordedStartOffset: Timeline.time(seconds: recordedOffset)
        )
    }

    private func transcript(_ words: [(Int, TimeInterval, TimeInterval, String)]) -> Transcript {
        Transcript(
            source: "microphone.m4a", engine: "test", language: "en",
            segments: [Transcript.Segment(
                id: 0,
                start: words.first?.1 ?? 0,
                end: words.last?.2 ?? 0,
                text: words.map(\.3).joined(separator: " "),
                words: words.map { Transcript.Word(id: $0.0, start: $0.1, end: $0.2, text: $0.3) }
            )]
        )
    }

    private func project(
        document: SessionEdit,
        transcript: Transcript? = nil,
        events: EventTimeline = EventTimeline(events: []),
        micRecordedOffset: TimeInterval = 0
    ) -> ReviewProjection {
        let probes = [probe(.screen), probe(.microphone, recordedOffset: micRecordedOffset)]
        let timeline = TimelineResolver.resolve(document: document, probes: probes)
        return ReviewProjector.project(
            timeline: timeline, document: document, transcript: transcript, events: events
        )
    }

    // MARK: - Regions tile the recording

    func testAnUneditedRecordingIsOneKeptRegion() {
        let projection = project(document: .initial(duration: 60))

        XCTAssertEqual(projection.regions.count, 1)
        XCTAssertFalse(projection.regions[0].isCut)
        XCTAssertEqual(projection.regions[0].span, StampSpan(start: 0, end: 60))
    }

    func testRegionsTileTheWholeRecordingWithoutGaps() throws {
        let document = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 10, end: 15)))
            .applying(.removeRange(TimeSpan(start: 40, end: 42)))

        let projection = project(document: document)

        XCTAssertEqual(projection.regions.map(\.isCut), [false, true, false, true, false])
        var cursor = 0.0
        for region in projection.regions {
            XCTAssertEqual(region.span.start.seconds, cursor, accuracy: 0.0001)
            cursor = region.span.end.seconds
        }
        XCTAssertEqual(cursor, 60, accuracy: 0.0001)
    }

    func testACutRegionCarriesEveryCutCoveringIt() throws {
        // A word cut inside a range cut: restoring the region must remove both, or the user
        // clicks a shaded region and nothing visibly changes.
        let document = try SessionEdit.initial(duration: 60)
            .applying(.excludeWords([ExcludedWord(id: 3, start: 12, end: 12.4, text: "um")]))
            .applying(.removeRange(TimeSpan(start: 10, end: 15)))

        let projection = project(document: document)
        let cut = try XCTUnwrap(projection.regions.first { $0.isCut })

        XCTAssertEqual(cut.cutIDs.count, 2)
        XCTAssertEqual(cut.span, StampSpan(start: 10, end: 15))
    }

    func testACutRegionIsLabelledWithWhatWasRemoved() throws {
        let document = try SessionEdit.initial(duration: 60)
            .applying(.excludeWords([ExcludedWord(id: 3, start: 12, end: 12.4, text: "um")]))

        let projection = project(document: document)
        let cut = try XCTUnwrap(projection.regions.first { $0.isCut })

        XCTAssertEqual(cut.label, "um")
    }

    func testAPlainRangeCutHasNoLabel() throws {
        let document = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 10, end: 15)))

        let projection = project(document: document)
        XCTAssertNil(projection.regions.first { $0.isCut }?.label)
    }

    func testRegionLookupIsByBinarySearchAndHalfOpen() throws {
        let document = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 10, end: 15)))

        let projection = project(document: document)

        XCTAssertEqual(projection.region(atSource: Stamp(5))?.isCut, false)
        XCTAssertEqual(projection.region(atSource: Stamp(10))?.isCut, true, "the cut owns its start")
        XCTAssertEqual(projection.region(atSource: Stamp(14.99))?.isCut, true)
        XCTAssertEqual(projection.region(atSource: Stamp(15))?.isCut, false, "and not its end")
        XCTAssertNil(projection.region(atSource: Stamp(99)))
    }

    func testProjectingTwiceGivesEqualProjections() throws {
        // Region ids are derived from their spans rather than freshly generated, so an
        // unchanged document yields an equal projection and SwiftUI's `.equatable()`
        // short-circuits still hold.
        let document = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 10, end: 15)))

        XCTAssertEqual(project(document: document), project(document: document))
    }

    // MARK: - Words on both clocks

    func testWordsCarryTheirSourceAndCompositionSpans() {
        let projection = project(
            document: .initial(duration: 60),
            transcript: transcript([(0, 1, 1.5, "hello"), (1, 2, 2.6, "world")])
        )

        XCTAssertEqual(projection.words.count, 2)
        XCTAssertEqual(projection.words[0].source, StampSpan(start: 1, end: 1.5))
        XCTAssertEqual(projection.words[0].composition, [StampSpan(start: 1, end: 1.5)])
        XCTAssertFalse(projection.words[0].isCut)
    }

    func testWordsAreShiftedByTheMicrophoneLaneOffset() {
        // The transcript is in the microphone file's clock; the lane is shifted later in the
        // composition to undo its capture delay. Getting this wrong put cuts beside the words
        // they named — twice.
        let projection = project(
            document: .initial(duration: 60),
            transcript: transcript([(0, 10, 10.4, "um")]),
            micRecordedOffset: 0.4
        )

        XCTAssertEqual(projection.micOffset, 0.4, accuracy: 0.0001)
        XCTAssertEqual(projection.words[0].source.start.seconds, 10.4, accuracy: 0.0001)
    }

    func testAWordAfterACutMovesEarlierOnTheEditedTimeline() throws {
        let document = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 5, end: 10)))

        let projection = project(
            document: document,
            transcript: transcript([(0, 20, 20.5, "later")])
        )

        XCTAssertEqual(projection.words[0].source, StampSpan(start: 20, end: 20.5))
        XCTAssertEqual(projection.words[0].composition, [StampSpan(start: 15, end: 15.5)])
    }

    func testACutWordHasNoCompositionSpan() throws {
        let document = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 10, end: 15)))

        let projection = project(
            document: document,
            transcript: transcript([(0, 12, 12.4, "um")])
        )

        XCTAssertTrue(projection.words[0].isCut)
        XCTAssertTrue(projection.words[0].composition.isEmpty)
    }

    func testAWordStraddlingACutReportsBothHalves() throws {
        let document = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 10, end: 12)))

        let projection = project(
            document: document,
            transcript: transcript([(0, 9, 13, "streeeetched")])
        )

        XCTAssertEqual(projection.words[0].composition.count, 2)
        XCTAssertFalse(projection.words[0].isCut)
    }

    func testWordLookupAtACompositionTime() {
        let projection = project(
            document: .initial(duration: 60),
            transcript: transcript([(0, 1, 1.5, "hello"), (1, 2, 2.6, "world")])
        )

        XCTAssertEqual(projection.word(atComposition: Stamp(1.2))?.text, "hello")
        XCTAssertEqual(projection.word(atComposition: Stamp(2.5))?.text, "world")
        XCTAssertNil(projection.word(atComposition: Stamp(1.8)), "the gap between words")
    }

    func testWordLookupIsCorrectAcrossManyWords() {
        // Binary search, since it runs on every playhead tick.
        let words = (0..<500).map { (id: $0, Double($0) * 0.5, Double($0) * 0.5 + 0.4, "w\($0)") }
        let projection = project(
            document: .initial(duration: 300),
            transcript: transcript(words.map { ($0.id, $0.1, $0.2, $0.3) })
        )

        for index in stride(from: 0, to: 500, by: 37) {
            XCTAssertEqual(
                projection.word(atComposition: Stamp(Double(index) * 0.5 + 0.1))?.id,
                index
            )
        }
    }

    // MARK: - Cues

    func testCuesAreAssembledFromTheirWords() {
        let projection = project(
            document: .initial(duration: 60),
            transcript: transcript([(0, 1, 1.5, "hello"), (1, 2, 2.6, "world")])
        )

        let cue = projection.cues.first
        XCTAssertEqual(cue?.source, StampSpan(start: 1, end: 2.6))
        XCTAssertEqual(cue?.wordIDs, [0, 1])
        XCTAssertEqual(cue?.composition, [StampSpan(start: 1, end: 1.5), StampSpan(start: 2, end: 2.6)])
    }

    func testACueIsCutOnlyWhenEveryWordIsCut() throws {
        let document = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 0.5, end: 3)))

        let projection = project(
            document: document,
            transcript: transcript([(0, 1, 1.5, "hello"), (1, 2, 2.6, "world")])
        )

        XCTAssertTrue(projection.cues[0].isCut)
    }

    // MARK: - Markers, and which are facts

    func testRecordingAndEditorialMarkersAreDistinguished() throws {
        let document = try SessionEdit.initial(duration: 60)
            .applying(.addMarker(EditMarker(at: 30, label: "mine")))
        let events = EventTimeline(events: [
            RecordingEvent(ts: 10, type: .userMarker, mediaTs: 10, label: "logged")
        ])

        let projection = project(document: document, events: events)

        XCTAssertEqual(projection.markers.count, 2)
        XCTAssertEqual(projection.markers[0].label, "logged")
        XCTAssertFalse(projection.markers[0].isEditorial)
        XCTAssertEqual(projection.markers[1].label, "mine")
        XCTAssertTrue(projection.markers[1].isEditorial)
        XCTAssertNotNil(projection.markers[1].editorialID)
    }

    func testAMarkerInsideACutClampsToTheCutBoundary() throws {
        let document = try SessionEdit.initial(duration: 60)
            .applying(.addMarker(EditMarker(at: 30, label: "inside")))
            .applying(.removeRange(TimeSpan(start: 20, end: 40)))

        let projection = project(document: document)
        let marker = try XCTUnwrap(projection.markers.first { $0.label == "inside" })

        XCTAssertEqual(marker.composition?.seconds ?? -1, 20, accuracy: 0.0001,
                       "clamped to where the cut begins, so it stays reachable")
    }

    // MARK: - Conversions

    func testCompositionAndSourceRoundTrip() throws {
        let document = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 10, end: 20)))

        let projection = project(document: document)

        let source = try XCTUnwrap(projection.sourceTime(forComposition: Stamp(15)))
        XCTAssertEqual(source.seconds, 25, accuracy: 0.0001)
        XCTAssertEqual(projection.compositionTime(forSource: source)?.seconds ?? -1, 15, accuracy: 0.0001)
    }

    func testASourceTimeInsideACutHasNoCompositionTime() throws {
        let document = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 10, end: 20)))

        let projection = project(document: document)

        XCTAssertNil(projection.compositionTime(forSource: Stamp(15)))
    }

    func testTheStartOfACutResolvesThroughTheBoundaryHelper() throws {
        // Half-open ranges mean a cut's start is the *exclusive* end of the clip before it, so
        // the ordinary lookup finds nothing there. This is the trap that has been rediscovered
        // per-caller twice.
        let document = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 10, end: 20)))

        let projection = project(document: document)

        XCTAssertNil(projection.compositionTime(forSource: Stamp(10)))
        XCTAssertEqual(projection.compositionTime(atCutBoundary: Stamp(10))?.seconds ?? -1, 10, accuracy: 0.0001)
        XCTAssertEqual(projection.nearestCompositionTime(forSource: Stamp(15))?.seconds ?? -1, 10, accuracy: 0.0001)
    }

    func testMicrophoneTimeRoundTrips() {
        let projection = project(
            document: .initial(duration: 60),
            transcript: transcript([(0, 10, 10.4, "um")]),
            micRecordedOffset: 0.4
        )

        let source = projection.sourceTime(forMic: Stamp(10))
        XCTAssertEqual(source.seconds, 10.4, accuracy: 0.0001)
        XCTAssertEqual(projection.micTime(forSource: source).seconds, 10, accuracy: 0.0001)
    }

    func testAudioFileTimeSubtractsTheLaneOffset() {
        let projection = project(document: .initial(duration: 60), micRecordedOffset: 0.4)

        XCTAssertEqual(
            projection.audioFileTime(forSource: Stamp(10.4), lane: .microphone),
            10,
            accuracy: 0.0001
        )
    }

    /// The inverse direction, which the waveform relies on to place its cached envelope.
    ///
    /// Regression: the view negated the lane offset by hand, so the whole-file trace drew
    /// shifted by *twice* the offset on the source axis — and it disagreed with the zoomed
    /// detail trace, which was correct. Both signs are pinned here.
    func testSourceTimeForAudioFileAddsTheLaneOffset() {
        let projection = project(document: .initial(duration: 60), micRecordedOffset: 0.4)

        // Bucket 0 of a file-time envelope sits at +offset on the recording's timeline.
        XCTAssertEqual(
            projection.sourceTime(forAudioFile: 0, lane: .microphone).seconds,
            0.4,
            accuracy: 0.0001,
            "file time 0 lands LATER on the recording's timeline, not earlier"
        )
        XCTAssertEqual(
            projection.sourceTime(forAudioFile: 10, lane: .microphone).seconds,
            10.4,
            accuracy: 0.0001
        )
    }

    func testAudioFileAndSourceConversionsAreExactInverses() {
        let projection = project(document: .initial(duration: 60), micRecordedOffset: 0.4)

        for lane in AudioLane.allCases {
            for seconds in [0.0, 0.4, 5.0, 42.125] {
                let roundTripped = projection.audioFileTime(
                    forSource: projection.sourceTime(forAudioFile: seconds, lane: lane),
                    lane: lane
                )
                XCTAssertEqual(roundTripped, seconds, accuracy: 0.0001, "\(lane) at \(seconds)")
            }
        }
    }

    /// A lane with no offset is where the sign bug hid: both signs agree at zero, so only a
    /// nonzero offset can catch it.
    func testAZeroOffsetLaneIsIdentityInBothDirections() {
        let projection = project(document: .initial(duration: 60), micRecordedOffset: 0)

        XCTAssertEqual(projection.sourceTime(forAudioFile: 7, lane: .microphone).seconds, 7, accuracy: 0.0001)
        XCTAssertEqual(projection.audioFileTime(forSource: Stamp(7), lane: .microphone), 7, accuracy: 0.0001)
    }

    /// Regression: a cut starting at t=0 has no preceding clip, so the cut-boundary lookup
    /// found nothing and clicking inside a leading cut selected the region without moving the
    /// playhead.
    func testNearestCompositionTimeInsideALeadingCut() throws {
        var document = SessionEdit.initial(duration: 60)
        document.cuts = [Cut(span: TimeSpan(start: 0, end: 10), origin: .range)]
        let projection = project(document: document)

        // Nothing survives before 10s, so the first kept moment is composition zero.
        let inside = try XCTUnwrap(projection.nearestCompositionTime(forSource: Stamp(4)))
        XCTAssertEqual(inside.seconds, 0, accuracy: 0.0001)

        let atStart = try XCTUnwrap(projection.nearestCompositionTime(forSource: Stamp(0)))
        XCTAssertEqual(atStart.seconds, 0, accuracy: 0.0001)
    }

    func testNearestCompositionTimeInsideATrailingCutLandsOnThePrecedingClip() throws {
        var document = SessionEdit.initial(duration: 60)
        document.cuts = [Cut(span: TimeSpan(start: 50, end: 60), origin: .range)]
        let projection = project(document: document)

        let inside = try XCTUnwrap(projection.nearestCompositionTime(forSource: Stamp(55)))
        XCTAssertEqual(inside.seconds, 50, accuracy: 0.0001, "should land at the end of what survives")
    }

    func testNearestCompositionTimeIsNilWhenNothingSurvives() {
        var document = SessionEdit.initial(duration: 60)
        document.cuts = [Cut(span: TimeSpan(start: 0, end: 60), origin: .range)]
        let projection = project(document: document)

        XCTAssertNil(projection.nearestCompositionTime(forSource: Stamp(30)))
    }

    // MARK: - Selection helpers

    func testCutsOverlappingAndContainedInASpan() throws {
        let document = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 10, end: 15)))
            .applying(.removeRange(TimeSpan(start: 30, end: 35)))

        let projection = project(document: document)
        let selection = StampSpan<Source>(start: 12, end: 40)

        XCTAssertEqual(projection.cutIDs(overlapping: selection).count, 2)
        // Only the second is wholly inside: partially un-cutting the first would have to
        // degrade it, so it is excluded.
        XCTAssertEqual(projection.cutIDs(containedIn: selection).count, 1)
    }

    func testKeptDurationDiffersFromTheSpanAfterCuts() throws {
        let document = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 10, end: 15)))

        let projection = project(document: document)
        let selection = StampSpan<Source>(start: 5, end: 25)

        XCTAssertEqual(selection.duration, 20)
        XCTAssertEqual(projection.keptDuration(in: selection), 15, accuracy: 0.0001)
    }

    func testWordsOverlappingASelection() {
        let projection = project(
            document: .initial(duration: 60),
            transcript: transcript([(0, 1, 1.5, "a"), (1, 5, 5.5, "b"), (2, 9, 9.5, "c")])
        )

        XCTAssertEqual(
            projection.words(overlapping: StampSpan(start: 4, end: 10)).map(\.text),
            ["b", "c"]
        )
    }

    // MARK: - Stamps

    func testStampSpanMapsTimeToFractionAndBack() {
        let span = StampSpan<Source>(start: 10, end: 20)

        XCTAssertEqual(span.fraction(of: Stamp(15)), 0.5, accuracy: 0.0001)
        XCTAssertEqual(span.stamp(atFraction: 0.5).seconds, 15, accuracy: 0.0001)
    }

    func testFractionIsClampedOutsideTheSpan() {
        let span = StampSpan<Source>(start: 10, end: 20)

        XCTAssertEqual(span.fraction(of: Stamp(5)), 0)
        XCTAssertEqual(span.fraction(of: Stamp(99)), 1)
    }

    func testAZeroWidthSpanDoesNotDivideByZero() {
        let span = StampSpan<Source>(start: 10, end: 10)

        XCTAssertEqual(span.fraction(of: Stamp(10)), 0)
        XCTAssertTrue(span.isEmpty)
    }

    func testNonFiniteStampsCollapseToZero() {
        XCTAssertEqual(Stamp<Source>(Double.nan).seconds, 0)
        XCTAssertEqual(Stamp<Source>(Double.infinity).seconds, 0)
    }

    func testEmptyProjectionIsUsable() {
        let projection = ReviewProjection.empty

        XCTAssertTrue(projection.regions.isEmpty)
        XCTAssertNil(projection.word(atComposition: Stamp(0)))
        XCTAssertNil(projection.region(atSource: Stamp(0)))
        XCTAssertEqual(projection.keptDuration(in: StampSpan(start: 0, end: 10)), 0)
    }
}
