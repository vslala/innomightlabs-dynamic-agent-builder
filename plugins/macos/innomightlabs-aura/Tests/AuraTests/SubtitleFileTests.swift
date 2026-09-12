import XCTest
@testable import Aura

final class SubtitleFileTests: XCTestCase {
    private func cue(
        id: Int,
        source: (Double, Double),
        composition: [(Double, Double)],
        text: String
    ) -> ProjectedCue {
        ProjectedCue(
            id: id,
            text: text,
            source: StampSpan(start: Stamp(source.0), end: Stamp(source.1)),
            composition: composition.map { StampSpan(start: Stamp($0.0), end: Stamp($0.1)) },
            wordIDs: []
        )
    }

    // MARK: - Timestamps

    func testTimestampFormats() {
        XCTAssertEqual(SubtitleFile.timestamp(0, separator: ","), "00:00:00,000")
        XCTAssertEqual(SubtitleFile.timestamp(1.5, separator: ","), "00:00:01,500")
        XCTAssertEqual(SubtitleFile.timestamp(3661.25, separator: ","), "01:01:01,250")
        XCTAssertEqual(SubtitleFile.timestamp(1.5, separator: "."), "00:00:01.500")
    }

    /// Milliseconds come from a rounded total, not the fractional part, so a value just under a
    /// second cannot render as `,1000`.
    func testTimestampNeverProducesAThousandMilliseconds() {
        XCTAssertEqual(SubtitleFile.timestamp(1.9999, separator: ","), "00:00:02,000")
        XCTAssertEqual(SubtitleFile.timestamp(59.9999, separator: ","), "00:01:00,000")
    }

    func testNegativeTimeIsClamped() {
        XCTAssertEqual(SubtitleFile.timestamp(-5, separator: ","), "00:00:00,000")
    }

    // MARK: - Entries

    func testEntriesUseCompositionTimes() throws {
        // The cue sits at 10s in the recording but at 4s on the edited timeline.
        let entries = SubtitleFile.entries(from: [
            cue(id: 0, source: (10, 12), composition: [(4, 6)], text: "hello")
        ])

        let entry = try XCTUnwrap(entries.first)
        XCTAssertEqual(entry.start, 4, accuracy: 0.0001)
        XCTAssertEqual(entry.end, 6, accuracy: 0.0001)
    }

    /// A cut cue has no composition span, so it must not appear in the file at all.
    func testCutCuesAreOmitted() {
        let entries = SubtitleFile.entries(from: [
            cue(id: 0, source: (0, 2), composition: [], text: "removed"),
            cue(id: 1, source: (2, 4), composition: [(0, 2)], text: "kept"),
        ])
        XCTAssertEqual(entries.map(\.text), ["kept"])
    }

    /// A cut through the middle of a cue leaves two spans, and the caption has to appear twice.
    func testASplitCueBecomesTwoEntries() {
        let entries = SubtitleFile.entries(from: [
            cue(id: 0, source: (0, 4), composition: [(0, 1.5), (1.5, 3)], text: "split phrase")
        ])
        XCTAssertEqual(entries.count, 2)
        XCTAssertEqual(entries.map(\.text), ["split phrase", "split phrase"])
    }

    func testEntriesAreSortedByStart() {
        // Once gaps close, spans from different cues interleave.
        let entries = SubtitleFile.entries(from: [
            cue(id: 0, source: (0, 2), composition: [(5, 7)], text: "later"),
            cue(id: 1, source: (2, 4), composition: [(0, 2)], text: "earlier"),
        ])
        XCTAssertEqual(entries.map(\.text), ["earlier", "later"])
    }

    func testSliversLeftByACutAreDropped() {
        let entries = SubtitleFile.entries(from: [
            cue(id: 0, source: (0, 4), composition: [(0, 0.05), (1, 3)], text: "phrase")
        ])
        XCTAssertEqual(entries.count, 1, "a 50ms caption would flash for a frame")
    }

    func testBlankCuesAreDropped() {
        let entries = SubtitleFile.entries(from: [
            cue(id: 0, source: (0, 2), composition: [(0, 2)], text: "   ")
        ])
        XCTAssertTrue(entries.isEmpty)
    }

    // MARK: - Rendering

    func testSRT() {
        let rendered = SubtitleFile.render(cues: [
            cue(id: 0, source: (0, 2), composition: [(0, 2)], text: "first"),
            cue(id: 1, source: (2, 4), composition: [(2, 4)], text: "second"),
        ], as: .srt)

        XCTAssertEqual(rendered, """
        1
        00:00:00,000 --> 00:00:02,000
        first

        2
        00:00:02,000 --> 00:00:04,000
        second

        """)
    }

    func testVTTHasItsHeaderAndDotSeparator() {
        let rendered = SubtitleFile.render(cues: [
            cue(id: 0, source: (0, 2), composition: [(0, 2)], text: "first")
        ], as: .vtt)

        XCTAssertTrue(rendered.hasPrefix("WEBVTT\n\n"))
        XCTAssertTrue(rendered.contains("00:00:00.000 --> 00:00:02.000"))
    }

    func testSRTNumbersEntriesNotCues() {
        // A split cue contributes two entries, which must be numbered 1 and 2.
        let rendered = SubtitleFile.render(cues: [
            cue(id: 0, source: (0, 4), composition: [(0, 1.5), (1.5, 3)], text: "phrase")
        ], as: .srt)

        XCTAssertTrue(rendered.hasPrefix("1\n"))
        XCTAssertTrue(rendered.contains("\n2\n"))
    }

    func testEmptyInputRendersEmpty() {
        XCTAssertEqual(SubtitleFile.render(cues: [], as: .srt), "")
        XCTAssertEqual(SubtitleFile.render(cues: [], as: .vtt), "WEBVTT\n\n")
    }
}
