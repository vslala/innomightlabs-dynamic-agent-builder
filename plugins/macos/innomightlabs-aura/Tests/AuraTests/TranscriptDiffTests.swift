import XCTest
@testable import Aura

final class TranscriptDiffTests: XCTestCase {
    func testAChangedWordIsAChange() {
        XCTAssertEqual(TranscriptDiff.changedText(from: "I like cats.", to: "I like dogs."), "I like dogs.")
    }

    func testIdenticalTextIsNotAChange() {
        XCTAssertNil(TranscriptDiff.changedText(from: "I like cats.", to: "I like cats."))
    }

    func testWhitespaceOnlyEditsAreNotChanges() {
        XCTAssertNil(TranscriptDiff.changedText(from: "I like cats.", to: "  I  like   cats. \n"))
    }

    func testEmptyingACueIsNotAReplacement() {
        // Removing speech is a cut, which already exists; speaking nothing is not an edit.
        XCTAssertNil(TranscriptDiff.changedText(from: "I like cats.", to: "   "))
    }

    func testTheCueSpanIsTakenFromItsWordsInSessionTime() throws {
        let cue = Transcript.Segment(id: 1, start: 9.8, end: 15.4, text: "Hello there.", words: [
            Transcript.Word(id: 0, start: 10, end: 10.4, text: "Hello"),
            Transcript.Word(id: 1, start: 10.5, end: 15, text: "there.")
        ])

        let span = try XCTUnwrap(TranscriptDiff.span(of: cue, micOffset: 0.4))
        XCTAssertEqual(span.start, 10.4, accuracy: 0.0001)
        XCTAssertEqual(span.end, 15.4, accuracy: 0.0001)
    }

    func testACueWithNoWordsHasNoSpan() {
        let cue = Transcript.Segment(id: 1, start: 1, end: 2, text: "", words: [])
        XCTAssertNil(TranscriptDiff.span(of: cue, micOffset: 0))
    }

    func testCameraVisibilityOverASpan() {
        var edit = SessionEdit.initial(duration: 30, cameraOverlay: [
            OverlayKeyframe(t: 0, rect: .defaultCameraOverlay, visible: false),
            OverlayKeyframe(t: 12, rect: .defaultCameraOverlay, visible: true),
            OverlayKeyframe(t: 20, rect: .defaultCameraOverlay, visible: false)
        ])

        XCTAssertFalse(edit.cameraIsVisible(during: TimeSpan(start: 2, end: 8)))
        XCTAssertTrue(edit.cameraIsVisible(during: TimeSpan(start: 10, end: 14)), "turns on inside the span")
        XCTAssertTrue(edit.cameraIsVisible(during: TimeSpan(start: 13, end: 18)), "on throughout")
        XCTAssertFalse(edit.cameraIsVisible(during: TimeSpan(start: 21, end: 25)))

        edit.cameraOverlay = []
        XCTAssertFalse(edit.cameraIsVisible(during: TimeSpan(start: 0, end: 5)))
    }
}
