import XCTest
@testable import Aura

final class ReviewKeyCommandTests: XCTestCase {
    private func resolve(
        _ characters: String,
        keyCode: UInt16 = 0,
        modifiers: ReviewKeyCommand.Modifiers = [],
        focus: ReviewKeyCommand.Focus = .timeline
    ) -> ReviewKeyCommand? {
        ReviewKeyCommand.resolve(characters: characters, keyCode: keyCode, modifiers: modifiers, focus: focus)
    }

    // MARK: - The bug this table exists to prevent

    func testSpaceWhileTypingIsNotACommand() {
        XCTAssertNil(resolve(" ", keyCode: 49, focus: .textInput))
    }

    func testDeleteWhileTypingIsNotACommand() {
        XCTAssertNil(resolve("", keyCode: 51, focus: .textInput))
        XCTAssertNil(resolve("", keyCode: 117, focus: .textInput))
    }

    func testLetterCommandsWhileTypingAreNotCommands() {
        XCTAssertNil(resolve("s", focus: .textInput))
        XCTAssertNil(resolve("m", focus: .textInput))
    }

    func testUndoInATextFieldBelongsToTheTextField() {
        // Otherwise Cmd+Z after a typo undoes the last timeline edit and the typed text is
        // unrecoverable.
        XCTAssertNil(resolve("z", modifiers: .command, focus: .textInput))
        XCTAssertNil(resolve("z", modifiers: [.command, .shift], focus: .textInput))
    }

    func testNonEditingCommandChordsStillWorkWhileTyping() {
        // Zoom has no meaning inside a text field, so the timeline keeps it.
        XCTAssertEqual(resolve("=", modifiers: .command, focus: .textInput), .zoomIn)
        XCTAssertEqual(resolve("0", modifiers: .command, focus: .textInput), .zoomToFit)
    }

    // MARK: - Transport

    func testSpaceTogglesPlayback() {
        XCTAssertEqual(resolve(" ", keyCode: 49), .togglePlayback)
    }

    func testBothDeleteKeysCut() {
        XCTAssertEqual(resolve("", keyCode: 51), .cutSelection)
        XCTAssertEqual(resolve("", keyCode: 117), .cutSelection)
    }

    func testEscapeClearsSelection() {
        XCTAssertEqual(resolve("", keyCode: 53), .clearSelection)
    }

    func testArrowsNudgeByOneFrameAndShiftNudgesByTen() {
        XCTAssertEqual(resolve("", keyCode: 123), .nudgePlayhead(frames: -1))
        XCTAssertEqual(resolve("", keyCode: 124), .nudgePlayhead(frames: 1))
        XCTAssertEqual(resolve("", keyCode: 123, modifiers: .shift), .nudgePlayhead(frames: -10))
        XCTAssertEqual(resolve("", keyCode: 124, modifiers: .shift), .nudgePlayhead(frames: 10))
    }

    func testSplitAndMarker() {
        XCTAssertEqual(resolve("s"), .splitAtPlayhead)
        XCTAssertEqual(resolve("m"), .addMarker)
    }

    // MARK: - Command chords

    func testUndoRedo() {
        XCTAssertEqual(resolve("z", modifiers: .command), .undo)
        XCTAssertEqual(resolve("z", modifiers: [.command, .shift]), .redo)
    }

    func testZoom() {
        XCTAssertEqual(resolve("=", modifiers: .command), .zoomIn)
        XCTAssertEqual(resolve("+", modifiers: .command), .zoomIn)
        XCTAssertEqual(resolve("-", modifiers: .command), .zoomOut)
        XCTAssertEqual(resolve("0", modifiers: .command), .zoomToFit)
    }

    // MARK: - Nothing swallowed by accident

    func testUnmappedKeysResolveToNil() {
        XCTAssertNil(resolve("q"))
        XCTAssertNil(resolve("x", modifiers: .command))
        XCTAssertNil(resolve("", keyCode: 200))
    }

    func testOptionAndControlChordsAreLeftAlone() {
        // Text navigation and system chords must reach whatever owns them.
        XCTAssertNil(resolve("s", modifiers: .option))
        XCTAssertNil(resolve(" ", keyCode: 49, modifiers: .control))
    }
}
