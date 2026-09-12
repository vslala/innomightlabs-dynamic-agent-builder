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

    /// Escape is the one bare key that has to work while typing: it is how you leave the
    /// command palette, and it never inserts a character.
    func testEscapeWorksEvenInATextField() {
        XCTAssertEqual(resolve("", keyCode: 53, focus: .textInput), .clearSelection)
    }

    func testArrowsSeekSmallAndShiftArrowsSeekLarge() {
        let small = ReviewKeyCommand.smallSeekFrames
        let large = ReviewKeyCommand.largeSeekFrames

        XCTAssertEqual(resolve("", keyCode: 123), .nudgePlayhead(frames: -small))
        XCTAssertEqual(resolve("", keyCode: 124), .nudgePlayhead(frames: small))
        XCTAssertEqual(resolve("", keyCode: 123, modifiers: .shift), .nudgePlayhead(frames: -large))
        XCTAssertEqual(resolve("", keyCode: 124, modifiers: .shift), .nudgePlayhead(frames: large))
        XCTAssertGreaterThan(large, small)
    }

    func testEditingKeys() {
        XCTAssertEqual(resolve("m"), .addMarker)
        XCTAssertEqual(resolve("i"), .markIn)
        XCTAssertEqual(resolve("o"), .markOut)
    }

    /// `B` arms the blade; splitting immediately is the command chord. Conflating them would
    /// mean a stray keystroke silently cutting the timeline.
    func testBladeIsAModeAndSplitIsACommandChord() {
        XCTAssertEqual(resolve("b"), .armBlade)
        XCTAssertEqual(resolve("b", modifiers: .command), .splitAtPlayhead)
    }

    func testShuttle() {
        XCTAssertEqual(resolve("j"), .shuttle(.reverse))
        XCTAssertEqual(resolve("k"), .shuttle(.stop))
        XCTAssertEqual(resolve("l"), .shuttle(.forward))
    }

    func testCommandPalette() {
        XCTAssertEqual(resolve("k", modifiers: .command), .commandPalette)
        // Cmd+K must beat the bare `k` shuttle binding.
        XCTAssertNotEqual(resolve("k", modifiers: .command), .shuttle(.stop))
    }

    func testBareZoomKeys() {
        XCTAssertEqual(resolve("+"), .zoomIn)
        XCTAssertEqual(resolve("="), .zoomIn)
        XCTAssertEqual(resolve("-"), .zoomOut)
    }

    /// Aura's timeline is derived from cuts and cannot hold a gap, so there is no "lift" to
    /// distinguish from a ripple delete. Both keys do the same thing on purpose.
    func testShiftDeleteIsTheSameRippleDeleteAsDelete() {
        XCTAssertEqual(resolve("", keyCode: 51), .cutSelection)
        XCTAssertEqual(resolve("", keyCode: 51, modifiers: .shift), .cutSelection)
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
