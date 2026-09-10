import XCTest
@testable import Aura

final class TranscriptTests: XCTestCase {
    private func transcript(_ spans: [(TimeInterval, TimeInterval)]) -> Transcript {
        Transcript(
            source: "microphone.m4a",
            engine: "whisperkit/openai_whisper-base",
            language: "en",
            segments: spans.enumerated().map { index, span in
                Transcript.Segment(id: index, start: span.0, end: span.1, text: "cue \(index)", words: nil)
            }
        )
    }

    func testRoundTripsThroughJSON() throws {
        var subject = transcript([(0, 2), (2, 5)])
        subject.segments[0].words = [
            Transcript.Word(start: 0.1, end: 0.4, text: "Hello"),
            Transcript.Word(start: 0.5, end: 0.9, text: "there")
        ]

        let data = try JSONEncoder().encode(subject)

        XCTAssertEqual(try JSONDecoder().decode(Transcript.self, from: data), subject)
    }

    func testLookupFindsTheSegmentCoveringATime() {
        let subject = transcript([(0, 2), (2, 5), (5, 9)])

        XCTAssertEqual(subject.segment(at: 0)?.id, 0)
        XCTAssertEqual(subject.segment(at: 1.9)?.id, 0)
        XCTAssertEqual(subject.segment(at: 3)?.id, 1)
        XCTAssertEqual(subject.segment(at: 8.99)?.id, 2)
    }

    func testLookupBoundariesAreHalfOpen() {
        let subject = transcript([(0, 2), (2, 5)])

        // 2 belongs to the second cue, not the first, so the highlight moves once rather
        // than flickering between them.
        XCTAssertEqual(subject.segment(at: 2)?.id, 1)
    }

    func testLookupOutsideAnySegmentReturnsNothing() {
        let subject = transcript([(1, 2), (4, 5)])

        XCTAssertNil(subject.segment(at: 0.5), "Before the first cue")
        XCTAssertNil(subject.segment(at: 3), "In the gap between cues")
        XCTAssertNil(subject.segment(at: 99), "Past the last cue")
    }

    func testLookupOnAnEmptyTranscriptReturnsNothing() {
        XCTAssertNil(transcript([]).segment(at: 0))
    }

    func testLookupIsCorrectAcrossManySegments() {
        // Binary search, since this runs on every playhead tick.
        let subject = transcript((0..<500).map { (Double($0), Double($0) + 1) })

        for index in 0..<500 {
            XCTAssertEqual(subject.segment(at: Double(index) + 0.5)?.id, index)
        }
    }

    func testLoadRejectsANewerSchema() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-transcript-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let url = directory.appendingPathComponent("transcript.json")
        var future = transcript([(0, 1)])
        future.schemaVersion = Transcript.currentSchemaVersion + 1
        try JSONEncoder().encode(future).write(to: url)

        XCTAssertNil(Transcript.load(from: url))
    }

    func testWriteThenLoadRoundTrips() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-transcript-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let url = directory.appendingPathComponent("transcript.json")
        let subject = transcript([(0, 2), (2, 5)])
        subject.write(to: url)

        XCTAssertEqual(Transcript.load(from: url), subject)
    }

    func testLoadOfAMissingFileIsNil() {
        let missing = FileManager.default.temporaryDirectory
            .appendingPathComponent("absent-\(UUID().uuidString).json")

        XCTAssertNil(Transcript.load(from: missing))
    }

    // MARK: - Placement on the composition timeline
    //
    // Transcript times are in mic media time, so they go through `micTimeOffset` and then the
    // time map. These pin that chain, which is where a 100-300ms desync would hide.

    func testCueSpanSurvivesAnEarlierCutShiftedEarlier() throws {
        let edit = try SessionEdit.initial(duration: 30)
            .applying(.removeRange(TimeSpan(start: 5, end: 10)))
        let cue = Transcript.Segment(id: 0, start: 20, end: 22, text: "later", words: nil)

        let spans = edit.timeMap.compositionSpans(forSource: cue.span)

        XCTAssertEqual(spans, [TimeSpan(start: 15, end: 17)])
    }

    func testCueInsideACutRangeMapsToNothing() throws {
        let edit = try SessionEdit.initial(duration: 30)
            .applying(.removeRange(TimeSpan(start: 5, end: 10)))
        let cue = Transcript.Segment(id: 0, start: 6, end: 8, text: "removed", words: nil)

        XCTAssertTrue(edit.timeMap.compositionSpans(forSource: cue.span).isEmpty)
    }

    func testMicOffsetShiftsCuesOntoTheSessionTimeline() {
        // If the decoder read the raw track it started counting at the first real sample,
        // which is late by the leading empty edit.
        let offset = 0.184
        let cue = Transcript.Segment(id: 0, start: 10, end: 12, text: "speech", words: nil)
        let edit = SessionEdit.initial(duration: 30, micTimeOffset: offset)

        let shifted = TimeSpan(start: cue.start + edit.micTimeOffset, end: cue.end + edit.micTimeOffset)
        let spans = edit.timeMap.compositionSpans(forSource: shifted)

        XCTAssertEqual(spans.first?.start ?? 0, 10.184, accuracy: 0.0001)
    }
}
