import XCTest
@testable import Aura

final class RecordingEventTests: XCTestCase {
    private struct DecodedEvent: Decodable {
        let ts: Double
        let type: String
        let app: String?
        let label: String?
        let path: String?
        let mediaTs: Double?

        private enum CodingKeys: String, CodingKey {
            case ts, type, app, label, path
            case mediaTs = "media_ts"
        }
    }

    private func encodeAndDecode(_ event: RecordingEvent) throws -> DecodedEvent {
        let data = try JSONEncoder().encode(event)
        return try JSONDecoder().decode(DecodedEvent.self, from: data)
    }

    func testUserMarkerRoundTripsWithLabel() throws {
        let decoded = try encodeAndDecode(RecordingEvent(ts: 52.4, type: .userMarker, label: "mistake"))
        XCTAssertEqual(decoded.type, "user_marker")
        XCTAssertEqual(decoded.label, "mistake")
        XCTAssertNil(decoded.app)
        XCTAssertNil(decoded.path)
    }

    func testScreenSnapshotRoundTripsWithPath() throws {
        let decoded = try encodeAndDecode(
            RecordingEvent(ts: 21.3, type: .screenSnapshot, path: "screenshots/21.3.png")
        )
        XCTAssertEqual(decoded.type, "screen_snapshot")
        XCTAssertEqual(decoded.path, "screenshots/21.3.png")
        XCTAssertNil(decoded.app)
        XCTAssertNil(decoded.label)
    }

    func testLabelAndPathOmittedWhenNil() throws {
        let data = try JSONEncoder().encode(RecordingEvent(ts: 1, type: .pause))
        let json = String(data: data, encoding: .utf8) ?? ""
        XCTAssertFalse(json.contains("\"label\""))
        XCTAssertFalse(json.contains("\"path\""))
        XCTAssertFalse(json.contains("\"app\""))
    }

    func testExistingEventKindsStillEncodeUnchanged() throws {
        let decoded = try encodeAndDecode(RecordingEvent(ts: 0, type: .recordStart, app: "Chrome"))
        XCTAssertEqual(decoded.type, "record_start")
        XCTAssertEqual(decoded.app, "Chrome")
        XCTAssertNil(decoded.label)
        XCTAssertNil(decoded.path)
    }

    func testMediaTimestampIsEncodedUnderSnakeCaseKey() throws {
        let decoded = try encodeAndDecode(RecordingEvent(ts: 20.5, type: .userMarker, mediaTs: 16.5, label: "here"))
        XCTAssertEqual(decoded.ts, 20.5)
        XCTAssertEqual(decoded.mediaTs, 16.5)
    }

    func testMediaTimestampOmittedWhenAbsent() throws {
        let data = try JSONEncoder().encode(RecordingEvent(ts: 1, type: .pause))
        let json = String(data: data, encoding: .utf8) ?? ""
        XCTAssertFalse(json.contains("media_ts"))
    }

    func testTrackFailureRoundTripsWithReason() throws {
        let decoded = try encodeAndDecode(RecordingEvent(ts: 9, type: .trackFailed, label: "camera.mov died"))
        XCTAssertEqual(decoded.type, "track_failed")
        XCTAssertEqual(decoded.label, "camera.mov died")
    }

    func testDecodesALogLineWrittenWithoutMediaTimestamp() throws {
        let line = #"{"ts":52.4,"type":"user_marker","label":"mistake"}"#
        let event = try JSONDecoder().decode(RecordingEvent.self, from: Data(line.utf8))

        XCTAssertEqual(event.ts, 52.4)
        XCTAssertEqual(event.type, .userMarker)
        XCTAssertEqual(event.label, "mistake")
        XCTAssertNil(event.mediaTs)
    }
}
