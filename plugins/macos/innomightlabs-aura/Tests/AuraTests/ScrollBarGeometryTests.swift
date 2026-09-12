import XCTest
@testable import Aura

final class ScrollBarGeometryTests: XCTestCase {
    private let track: CGFloat = 800
    private let total: TimeInterval = 400

    private func thumb(
        viewportStart: TimeInterval,
        visible: TimeInterval,
        trackWidth: CGFloat? = nil
    ) -> ScrollBarGeometry.Thumb? {
        ScrollBarGeometry.thumb(
            viewportStart: viewportStart,
            visibleDuration: visible,
            recordingDuration: total,
            trackWidth: trackWidth ?? track
        )
    }

    // MARK: - Nothing to scroll

    func testNoThumbWhenTheWholeRecordingFits() {
        XCTAssertNil(thumb(viewportStart: 0, visible: total))
        XCTAssertNil(thumb(viewportStart: 0, visible: total + 100))
    }

    func testNoThumbForDegenerateInputs() {
        XCTAssertNil(thumb(viewportStart: 0, visible: 0))
        XCTAssertNil(thumb(viewportStart: 0, visible: 20, trackWidth: 0))
        XCTAssertNil(
            ScrollBarGeometry.thumb(
                viewportStart: 0, visibleDuration: 20, recordingDuration: 0, trackWidth: track
            )
        )
    }

    // MARK: - Proportions

    func testThumbWidthIsProportionalToWhatIsVisible() throws {
        // A quarter of the recording visible gives a quarter-width thumb.
        let quarter = try XCTUnwrap(thumb(viewportStart: 0, visible: 100))
        XCTAssertEqual(quarter.width, 200, accuracy: 0.001)

        let tenth = try XCTUnwrap(thumb(viewportStart: 0, visible: 40))
        XCTAssertEqual(tenth.width, 80, accuracy: 0.001)
    }

    /// At extreme zoom the proportional thumb would be sub-pixel and impossible to grab.
    func testThumbHasAMinimumWidth() throws {
        let tiny = try XCTUnwrap(thumb(viewportStart: 0, visible: 0.5))
        XCTAssertEqual(tiny.width, ScrollBarGeometry.minimumThumbWidth, accuracy: 0.001)
    }

    func testThumbNeverExceedsTheTrack() throws {
        let wide = try XCTUnwrap(thumb(viewportStart: 0, visible: 399.9, trackWidth: 20))
        XCTAssertLessThanOrEqual(wide.width, 20)
    }

    // MARK: - Position

    func testThumbSitsAtTheStartWhenNotScrolled() throws {
        XCTAssertEqual(try XCTUnwrap(thumb(viewportStart: 0, visible: 100)).x, 0, accuracy: 0.001)
    }

    /// The thumb's own width is unavailable to it, so full scroll puts its trailing edge — not
    /// its origin — at the end of the track.
    func testFullyScrolledThumbEndsFlushWithTheTrack() throws {
        let end = try XCTUnwrap(thumb(viewportStart: total - 100, visible: 100))
        XCTAssertEqual(end.x + end.width, track, accuracy: 0.001)
    }

    func testThumbIsClampedForOutOfRangeViewports() throws {
        let past = try XCTUnwrap(thumb(viewportStart: 10_000, visible: 100))
        XCTAssertEqual(past.x + past.width, track, accuracy: 0.001)

        let before = try XCTUnwrap(thumb(viewportStart: -50, visible: 100))
        XCTAssertEqual(before.x, 0, accuracy: 0.001)
    }

    // MARK: - Round trip
    //
    // The property that matters when dragging: if the two directions disagree about the
    // thumb's shortened travel, the thumb drifts away from the cursor mid-drag.

    func testThumbPositionRoundTripsToTheSameViewport() throws {
        for visible in [100.0, 40.0, 5.0, 0.5] {
            for viewportStart in [0.0, 13.7, 200.0, total - visible] {
                let thumb = try XCTUnwrap(self.thumb(viewportStart: viewportStart, visible: visible))
                let recovered = ScrollBarGeometry.viewportStart(
                    thumbX: thumb.x,
                    thumbWidth: thumb.width,
                    visibleDuration: visible,
                    recordingDuration: total,
                    trackWidth: track
                )
                XCTAssertEqual(
                    recovered, viewportStart, accuracy: 0.01,
                    "visible=\(visible) start=\(viewportStart)"
                )
            }
        }
    }

    func testDraggingToTheTrackEndsGivesTheViewportExtremes() throws {
        let thumb = try XCTUnwrap(self.thumb(viewportStart: 0, visible: 100))

        let atStart = ScrollBarGeometry.viewportStart(
            thumbX: -500, thumbWidth: thumb.width,
            visibleDuration: 100, recordingDuration: total, trackWidth: track
        )
        XCTAssertEqual(atStart, 0, accuracy: 0.001)

        let atEnd = ScrollBarGeometry.viewportStart(
            thumbX: 5_000, thumbWidth: thumb.width,
            visibleDuration: 100, recordingDuration: total, trackWidth: track
        )
        XCTAssertEqual(atEnd, total - 100, accuracy: 0.001, "should reach the last window, no further")
    }

    func testViewportStartIsZeroWhenThereIsNoTravel() {
        // A thumb filling the track cannot move, and must not divide by zero.
        XCTAssertEqual(
            ScrollBarGeometry.viewportStart(
                thumbX: 100, thumbWidth: track,
                visibleDuration: 100, recordingDuration: total, trackWidth: track
            ),
            0
        )
    }

    func testThumbMovesMonotonicallyWithTheViewport() throws {
        var previous: CGFloat = -1
        for start in stride(from: 0.0, through: total - 100, by: 10) {
            let thumb = try XCTUnwrap(self.thumb(viewportStart: start, visible: 100))
            XCTAssertGreaterThan(thumb.x, previous, "thumb went backwards at \(start)")
            previous = thumb.x
        }
    }
}
