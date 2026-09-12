import XCTest
@testable import Aura

final class PlayheadFollowerTests: XCTestCase {
    private let leadIn = PlayheadFollower.leadInFraction
    private let total: TimeInterval = 400

    private func start(
        playhead: TimeInterval,
        windowStart: TimeInterval,
        windowDuration: TimeInterval = 20,
        recordingDuration: TimeInterval? = nil
    ) -> TimeInterval? {
        PlayheadFollower.viewportStart(
            playhead: playhead,
            window: (start: windowStart, duration: windowDuration),
            recordingDuration: recordingDuration ?? total,
            leadInFraction: leadIn
        )
    }

    // MARK: - The whole point: it holds still while the playhead is visible

    func testDoesNotMoveWhileThePlayheadIsInsideTheWindow() {
        for playhead in [10.0, 10.5, 20.0, 25.0, 29.9] {
            XCTAssertNil(start(playhead: playhead, windowStart: 10), "moved for \(playhead)")
        }
    }

    /// The property that makes this cheap: a cut can teleport the playhead a long way, and as
    /// long as it lands inside the window nothing scrolls and no waveform is re-read.
    func testACutJumpInsideTheWindowCostsNothing() {
        XCTAssertNil(start(playhead: 28, windowStart: 10), "a jump from 11s to 28s stays put")
    }

    // MARK: - Paging

    func testPagesForwardWhenThePlayheadLeavesTheTrailingEdge() throws {
        let new = try XCTUnwrap(start(playhead: 30, windowStart: 10))
        // The playhead lands one lead-in inside the new window, buying nearly a full window of
        // lookahead before the next move.
        XCTAssertEqual(new, 30 - 20 * leadIn, accuracy: 0.0001)
        XCTAssertLessThan(new + 20 * leadIn, new + 20, "playhead must be inside the new window")
    }

    /// Half-open, like the rest of the timeline: sitting exactly on the trailing edge is
    /// already outside.
    func testThePlayheadExactlyOnTheTrailingEdgePages() {
        XCTAssertNotNil(start(playhead: 30, windowStart: 10))
    }

    func testThePlayheadExactlyOnTheLeadingEdgeDoesNotPage() {
        XCTAssertNil(start(playhead: 10, windowStart: 10))
    }

    func testPagesBackwardsAfterASeekBehindTheWindow() throws {
        let new = try XCTUnwrap(start(playhead: 5, windowStart: 100))
        XCTAssertEqual(new, max(0, 5 - 20 * leadIn), accuracy: 0.0001)
    }

    func testOnePageMoveIsEnoughToContainThePlayhead() {
        // Whatever the jump, the playhead must be inside the window the move produces —
        // otherwise the next tick pages again and the view stutters.
        for playhead in [30.0, 45.0, 120.0, 399.0, 0.0, 5.0] {
            guard let new = start(playhead: playhead, windowStart: 100) else { continue }
            XCTAssertGreaterThanOrEqual(playhead, new, "playhead \(playhead) fell before the window")
            XCTAssertLessThan(playhead, new + 20, "playhead \(playhead) fell past the window")
        }
    }

    // MARK: - Clamping

    func testNeverScrollsPastTheEndOfTheRecording() throws {
        let new = try XCTUnwrap(start(playhead: 399, windowStart: 10))
        XCTAssertEqual(new, total - 20, accuracy: 0.0001)
    }

    func testNeverScrollsBeforeTheStart() throws {
        let new = try XCTUnwrap(start(playhead: 0.5, windowStart: 100))
        XCTAssertEqual(new, 0, accuracy: 0.0001)
    }

    // MARK: - Nothing to do

    func testDoesNothingWhenTheWholeRecordingIsVisible() {
        XCTAssertNil(start(playhead: 300, windowStart: 0, windowDuration: 400))
        XCTAssertNil(start(playhead: 300, windowStart: 0, windowDuration: 500))
    }

    func testDoesNothingForADegenerateWindow() {
        XCTAssertNil(start(playhead: 10, windowStart: 0, windowDuration: 0))
        XCTAssertNil(start(playhead: 10, windowStart: 0, windowDuration: -5))
    }

    // MARK: - Paging is rare, which is the reason for the design

    /// A continuous-tracking implementation would scroll on every tick the playhead moves.
    /// Paging must scroll a small number of times across a whole playthrough.
    func testPagingAcrossAWholeRecordingMovesOncePerWindow() {
        var windowStart: TimeInterval = 0
        var moves = 0
        let windowDuration: TimeInterval = 20

        // 30 ticks a second over 400s, which is what the real time observer delivers.
        for tick in 0...(400 * 30) {
            let playhead = Double(tick) / 30
            if let new = start(
                playhead: playhead,
                windowStart: windowStart,
                windowDuration: windowDuration
            ) {
                windowStart = new
                moves += 1
            }
        }

        // 400s of recording in ~17.6s effective pages (a window less its lead-in).
        XCTAssertLessThanOrEqual(moves, 25, "paging should be rare; got \(moves) moves")
        XCTAssertGreaterThan(moves, 15, "and it must actually keep up")
    }
}
