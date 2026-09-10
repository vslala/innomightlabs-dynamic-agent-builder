import XCTest
import CoreMedia
@testable import Aura

final class TimeMapTests: XCTestCase {
    private func map(_ spans: [(TimeInterval, TimeInterval)]) -> TimeMap {
        TimeMap(clips: spans.map { TimelineClip(source: TimeSpan(start: $0.0, end: $0.1)) })
    }

    func testUneditedTimelineMapsOneToOne() {
        let timeMap = map([(0, 30)])

        XCTAssertEqual(timeMap.duration, 30)
        XCTAssertEqual(timeMap.sourceTime(forComposition: 12), 12)
        XCTAssertEqual(timeMap.compositionTimes(forSource: 12), [12])
    }

    func testCutRangeShiftsLaterContentEarlier() {
        // 0-10 and 20-30 survive; the 10-20 range was cut.
        let timeMap = map([(0, 10), (20, 30)])

        XCTAssertEqual(timeMap.duration, 20)
        XCTAssertEqual(timeMap.sourceTime(forComposition: 5), 5)
        XCTAssertEqual(timeMap.sourceTime(forComposition: 12), 22)
        XCTAssertEqual(timeMap.compositionTimes(forSource: 22), [12])
    }

    func testSourceTimeInsideACutRangeMapsNowhere() {
        let timeMap = map([(0, 10), (20, 30)])
        XCTAssertEqual(timeMap.compositionTimes(forSource: 15), [])
    }

    func testDuplicatedClipMakesOneSourceTimeAppearTwice() {
        let timeMap = map([(0, 10), (0, 10)])

        XCTAssertEqual(timeMap.duration, 20)
        XCTAssertEqual(timeMap.compositionTimes(forSource: 4), [4, 14])
    }

    func testBoundariesAreHalfOpenSoACutDoesNotFlicker() {
        let timeMap = map([(0, 10), (20, 30)])

        // 10 is the first instant of the second clip, not the last of the first.
        XCTAssertEqual(timeMap.sourceTime(forComposition: 10), 20)
        // The very end of the timeline plays nothing.
        XCTAssertNil(timeMap.sourceTime(forComposition: 20))
        XCTAssertEqual(timeMap.compositionTimes(forSource: 10), [])
        XCTAssertEqual(timeMap.compositionTimes(forSource: 20), [10])
    }

    func testCompositionTimeBeyondTheEndMapsNowhere() {
        let timeMap = map([(0, 10)])
        XCTAssertNil(timeMap.sourceTime(forComposition: 99))
    }

    func testEmptyTimelineHasZeroDurationAndMapsNothing() {
        let timeMap = map([])

        XCTAssertEqual(timeMap.duration, 0)
        XCTAssertNil(timeMap.sourceTime(forComposition: 0))
        XCTAssertEqual(timeMap.compositionTimes(forSource: 0), [])
    }

    func testZeroLengthClipsAreDroppedRatherThanProducingEmptySegments() {
        let timeMap = map([(0, 10), (10, 10), (20, 25)])

        XCTAssertEqual(timeMap.segments.count, 2)
        XCTAssertEqual(timeMap.duration, 15)
    }

    func testSourceSpanSplitByACutMapsToTwoCompositionSpans() {
        // A transcript cue running 8-22 straddles the 10-20 cut.
        let timeMap = map([(0, 10), (20, 30)])
        let spans = timeMap.compositionSpans(forSource: TimeSpan(start: 8, end: 22))

        XCTAssertEqual(spans.count, 2)
        XCTAssertEqual(spans[0], TimeSpan(start: 8, end: 10))
        XCTAssertEqual(spans[1], TimeSpan(start: 10, end: 12))
    }

    func testSourceSpanEntirelyCutMapsToNoCompositionSpans() {
        let timeMap = map([(0, 10), (20, 30)])
        XCTAssertTrue(timeMap.compositionSpans(forSource: TimeSpan(start: 12, end: 18)).isEmpty)
    }

    func testEmptySourceSpanMapsToNothing() {
        let timeMap = map([(0, 30)])
        XCTAssertTrue(timeMap.compositionSpans(forSource: TimeSpan(start: 5, end: 5)).isEmpty)
    }

    func testSegmentsAreContiguousOnTheCompositionTimeline() {
        let timeMap = map([(0, 10), (20, 30), (40, 41)])

        var expectedStart = CMTime.zero
        for segment in timeMap.segments {
            XCTAssertEqual(segment.composition.start, expectedStart)
            expectedStart = segment.composition.end
        }
        XCTAssertEqual(expectedStart, timeMap.cmDuration)
    }

    func testFractionalTimesSnapToTheCanonicalTimescale() {
        let timeMap = map([(0, 1.0 / 3.0)])

        for segment in timeMap.segments {
            XCTAssertEqual(segment.source.start.timescale, Timeline.timescale)
            XCTAssertEqual(segment.source.duration.timescale, Timeline.timescale)
        }
    }
}
