import XCTest
@testable import Aura

/// The digest's non-trimmable fields must be bounded, or the prompt overflows the server's
/// hard 32,000-character cap with no way to recover — `fitting` can only shrink `outline` and
/// `words`.
final class SessionDigestCapTests: XCTestCase {
    private func documentWithManyFillerCuts(_ count: Int) -> SessionEdit {
        var document = SessionEdit.initial(duration: 3_600)
        document.cuts = (0..<count).map { index in
            let start = Double(index) * 0.5
            return Cut(span: TimeSpan(start: start, end: start + 0.2), origin: .filler(word: "um"))
        }
        document.splitPoints = (0..<count).map { Double($0) * 0.5 + 0.3 }
        document.markers = (0..<count).map { EditMarker(at: Double($0) * 0.5, label: "marker \($0)") }
        return document
    }

    func testHundredsOfFillerCutsStillFitTheCap() {
        // A filler sweep is the realistic way to mint hundreds of cuts at once, each carrying
        // a 36-character UUID.
        let document = documentWithManyFillerCuts(500)
        let digest = SessionDigest.make(
            sessionID: "s",
            duration: 3_600,
            probes: [],
            events: EventTimeline(events: []),
            document: document,
            transcript: nil
        )

        XCTAssertEqual(digest.rangeCuts.count, SessionDigest.maxRangeCuts)
        XCTAssertEqual(digest.rangeCutsOmitted, 500 - SessionDigest.maxRangeCuts)
        XCTAssertEqual(digest.editMarkers.count, SessionDigest.maxEditMarkers)
        XCTAssertEqual(digest.splits.count, SessionDigest.maxSplits)

        let prompt = EditSuggestionPrompt.build(
            instruction: "what did you cut?",
            context: EditSuggestionContext(
                sessionID: "s",
                duration: 3_600,
                transcript: nil,
                document: document,
                markers: [],
                digest: digest
            ),
            characterBudget: 32_000
        )
        XCTAssertLessThanOrEqual(prompt.count, 32_000, "capped lists must keep the prompt under the hard cap")
    }

    func testTheCapKeepsTheLongestCuts() {
        var document = SessionEdit.initial(duration: 3_600)
        // Many trivial cuts plus one long one, which is the one a user would ask about.
        document.cuts = (0..<200).map { index in
            let start = Double(index) * 1.0
            return Cut(span: TimeSpan(start: start, end: start + 0.1), origin: .filler(word: "um"))
        }
        document.cuts.append(Cut(span: TimeSpan(start: 900, end: 960), origin: .range))

        let digest = SessionDigest.make(
            sessionID: "s",
            duration: 3_600,
            probes: [],
            events: EventTimeline(events: []),
            document: document,
            transcript: nil
        )
        XCTAssertTrue(
            digest.rangeCuts.contains { $0.start == 900 && $0.end == 960 },
            "the 60-second cut must survive the cap ahead of 0.1s fillers"
        )
    }

    /// `keptSpans` and `excludedWordIds` are also untrimmable, and `keptSpans` has no natural
    /// bound — it derives from every user/agent range cut.
    func testHeavilyHandEditedDocumentsStillFitTheCap() {
        var document = SessionEdit.initial(duration: 7_200)
        // 900 user range cuts, the realistic result of a long manual edit session.
        document.cuts = (0..<900).map { index in
            let start = Double(index) * 8.0
            return Cut(span: TimeSpan(start: start, end: start + 4.0), origin: .range)
        }

        let digest = SessionDigest.make(
            sessionID: "s",
            duration: 7_200,
            probes: [],
            events: EventTimeline(events: []),
            document: document,
            transcript: nil
        )
        XCTAssertEqual(digest.keptSpans.count, SessionDigest.maxKeptSpans)
        XCTAssertGreaterThan(digest.keptSpansOmitted, 0)

        let prompt = EditSuggestionPrompt.build(
            instruction: "what survives?",
            context: EditSuggestionContext(
                sessionID: "s",
                duration: 7_200,
                transcript: nil,
                document: document,
                markers: [],
                digest: digest
            ),
            characterBudget: 32_000
        )
        XCTAssertLessThanOrEqual(prompt.count, 32_000)
    }

    func testThousandsOfWordCutsStillFitTheCap() {
        var document = SessionEdit.initial(duration: 7_200)
        document.cuts = (0..<3_000).map { index in
            let start = Double(index) * 2.0
            return Cut(
                span: TimeSpan(start: start, end: start + 0.2),
                origin: .word(id: index, text: "w\(index)")
            )
        }

        let digest = SessionDigest.make(
            sessionID: "s",
            duration: 7_200,
            probes: [],
            events: EventTimeline(events: []),
            document: document,
            transcript: nil
        )
        XCTAssertEqual(digest.excludedWordIds.count, SessionDigest.maxExcludedWordIds)
        XCTAssertEqual(digest.excludedWordIdsOmitted, 3_000 - SessionDigest.maxExcludedWordIds)
        XCTAssertLessThanOrEqual(digest.compactJSON().count, 32_000)
    }

    func testSmallDocumentsAreNotTruncated() {
        let document = documentWithManyFillerCuts(3)
        let digest = SessionDigest.make(
            sessionID: "s",
            duration: 3_600,
            probes: [],
            events: EventTimeline(events: []),
            document: document,
            transcript: nil
        )
        XCTAssertEqual(digest.rangeCuts.count, 3)
        XCTAssertEqual(digest.rangeCutsOmitted, 0)
        XCTAssertEqual(digest.editMarkersOmitted, 0)
        XCTAssertEqual(digest.splitsOmitted, 0)
        // Ordered by time for reading, even though the cap selects by length.
        XCTAssertEqual(digest.rangeCuts.map(\.start), digest.rangeCuts.map(\.start).sorted())
    }
}
