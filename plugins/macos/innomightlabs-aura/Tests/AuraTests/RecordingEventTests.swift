import XCTest
@testable import Aura

final class RecordingEventTests: XCTestCase {
    private struct DecodedEvent: Decodable {
        let ts: Double
        let type: String
        let app: String?
        let label: String?
        let path: String?
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
}
