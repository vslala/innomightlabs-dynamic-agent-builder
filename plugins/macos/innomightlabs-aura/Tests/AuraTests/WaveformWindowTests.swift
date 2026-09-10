import XCTest
@testable import Aura

final class WaveformWindowTests: XCTestCase {
    private func span(_ visible: TimeInterval?, playhead: TimeInterval, total: TimeInterval = 100) -> TimeSpan {
        WaveformWindow.span(total: total, visibleDuration: visible, playhead: playhead)
    }

    func testUnzoomedShowsTheWholeRecording() {
        XCTAssertEqual(span(nil, playhead: 40), TimeSpan(start: 0, end: 100))
    }

    func testWindowWiderThanTheRecordingShowsTheWholeThing() {
        XCTAssertEqual(span(500, playhead: 40), TimeSpan(start: 0, end: 100))
    }

    func testWindowCentresOnThePlayhead() {
        XCTAssertEqual(span(10, playhead: 50), TimeSpan(start: 45, end: 55))
    }

    func testWindowClampsAtTheStartSoTheOpeningIsReachable() {
        XCTAssertEqual(span(10, playhead: 0), TimeSpan(start: 0, end: 10))
        XCTAssertEqual(span(10, playhead: 2), TimeSpan(start: 0, end: 10))
    }

    func testWindowClampsAtTheEndSoTheFinalMomentIsReachable() {
        XCTAssertEqual(span(10, playhead: 100), TimeSpan(start: 90, end: 100))
        XCTAssertEqual(span(10, playhead: 98), TimeSpan(start: 90, end: 100))
    }

    func testWindowIsAlwaysTheRequestedWidthWhenItFits() {
        for playhead in stride(from: 0.0, through: 100.0, by: 7) {
            XCTAssertEqual(span(12, playhead: playhead).duration, 12, accuracy: 0.0001)
        }
    }

    func testWindowStaysInsideTheTimeline() {
        for playhead in stride(from: -50.0, through: 150.0, by: 11) {
            let window = span(9, playhead: playhead)
            XCTAssertGreaterThanOrEqual(window.start, 0)
            XCTAssertLessThanOrEqual(window.end, 100.0001)
        }
    }

    func testEmptyTimelineYieldsAnEmptyWindowRatherThanDividingByZero() {
        XCTAssertEqual(span(10, playhead: 0, total: 0), TimeSpan(start: 0, end: 0))
        XCTAssertEqual(span(nil, playhead: 0, total: 0), TimeSpan(start: 0, end: 0))
    }

    func testNonPositiveVisibleDurationFallsBackToTheWholeRecording() {
        XCTAssertEqual(span(0, playhead: 50), TimeSpan(start: 0, end: 100))
        XCTAssertEqual(span(-5, playhead: 50), TimeSpan(start: 0, end: 100))
    }
}
