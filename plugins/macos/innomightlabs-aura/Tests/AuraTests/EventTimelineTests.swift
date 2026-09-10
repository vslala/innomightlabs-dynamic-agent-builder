import XCTest
@testable import Aura

final class EventTimelineTests: XCTestCase {
    private func mediaTimes(_ events: [RecordingEvent]) -> [TimeInterval] {
        EventTimeline(events: events).entries.map(\.mediaTs)
    }

    func testWithoutPausesMediaTimeEqualsWallClock() {
        let times = mediaTimes([
            RecordingEvent(ts: 0, type: .recordStart),
            RecordingEvent(ts: 12, type: .userMarker, label: "here"),
            RecordingEvent(ts: 30, type: .recordStop)
        ])
        XCTAssertEqual(times, [0, 12, 30])
    }

    func testEventAfterPauseIsShiftedBackByPausedDuration() {
        let times = mediaTimes([
            RecordingEvent(ts: 0, type: .recordStart),
            RecordingEvent(ts: 10, type: .pause),
            RecordingEvent(ts: 14, type: .resume), // 4s paused
            RecordingEvent(ts: 20, type: .userMarker, label: "here")
        ])
        XCTAssertEqual(times, [0, 10, 10, 16])
    }

    func testMultiplePausesAccumulate() {
        let times = mediaTimes([
            RecordingEvent(ts: 5, type: .pause),
            RecordingEvent(ts: 7, type: .resume),  // +2s
            RecordingEvent(ts: 20, type: .pause),
            RecordingEvent(ts: 25, type: .resume), // +5s
            RecordingEvent(ts: 30, type: .recordStop)
        ])
        XCTAssertEqual(times, [5, 5, 18, 18, 23])
    }

    func testEventLoggedWhilePausedCollapsesToThePausePoint() {
        // `mark()` and `screenshot()` are both legal while paused, but the paused span is
        // not present in the media files, so there is only one media time they can mean.
        let times = mediaTimes([
            RecordingEvent(ts: 10, type: .pause),
            RecordingEvent(ts: 12, type: .userMarker, label: "while paused"),
            RecordingEvent(ts: 18, type: .resume)
        ])
        XCTAssertEqual(times, [10, 10, 10])
    }

    func testPersistedMediaTimeTakesPrecedenceOverRecovery() {
        let times = mediaTimes([
            RecordingEvent(ts: 20, type: .userMarker, mediaTs: 16, label: "here")
        ])
        XCTAssertEqual(times, [16])
    }

    func testResumeWithoutPauseIsIgnored() {
        let times = mediaTimes([
            RecordingEvent(ts: 5, type: .resume),
            RecordingEvent(ts: 9, type: .recordStop)
        ])
        XCTAssertEqual(times, [5, 9])
    }

    func testRepeatedPauseDoesNotRestartTheSpan() {
        let times = mediaTimes([
            RecordingEvent(ts: 10, type: .pause),
            RecordingEvent(ts: 12, type: .pause),
            RecordingEvent(ts: 20, type: .resume),
            RecordingEvent(ts: 25, type: .recordStop)
        ])
        XCTAssertEqual(times, [10, 10, 10, 15])
    }

    func testMarkersAndFailedTracksAreFilteredOut() {
        let timeline = EventTimeline(events: [
            RecordingEvent(ts: 0, type: .recordStart),
            RecordingEvent(ts: 4, type: .userMarker, label: "one"),
            RecordingEvent(ts: 6, type: .screenSnapshot, path: "screenshots/6.0.png"),
            RecordingEvent(ts: 9, type: .trackFailed, label: "camera.mov died"),
            RecordingEvent(ts: 11, type: .userMarker, label: "two")
        ])

        XCTAssertEqual(timeline.markers.map { $0.event.label }, ["one", "two"])
        XCTAssertEqual(timeline.screenshots.map(\.mediaTs), [6])
        XCTAssertEqual(timeline.failedTracks.map { $0.event.label }, ["camera.mov died"])
    }

    func testLoadSkipsMalformedLinesAndConvertsTheRest() throws {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("events-\(UUID().uuidString).jsonl")
        let contents = """
        {"ts":0,"type":"record_start"}
        {"ts":10,"type":"pause"}
        not json at all
        {"ts":14,"type":"resume"}
        {"ts":20,"type":"user_marker","label":"here"}
        {"ts":22,"type":
        """
        try contents.write(to: url, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: url) }

        let timeline = EventTimeline.load(eventsURL: url)

        XCTAssertEqual(timeline.entries.map(\.mediaTs), [0, 10, 10, 16])
        XCTAssertEqual(timeline.markers.first?.event.label, "here")
    }

    func testLoadOfMissingFileIsEmptyRatherThanAFailure() {
        let missing = FileManager.default.temporaryDirectory
            .appendingPathComponent("absent-\(UUID().uuidString).jsonl")
        XCTAssertTrue(EventTimeline.load(eventsURL: missing).entries.isEmpty)
    }
}
