import XCTest
@testable import Aura

final class TrackKindTests: XCTestCase {
    /// The recording picker and the timeline name the same three tracks — Screen, Camera,
    /// Voice — and must not drift apart into two vocabularies for one recording.
    func testTitleAndSymbolAgreeWithTimelineLane() {
        let overlapping: [(TrackKind, TimelineLane)] = [
            (.screen, .screen),
            (.camera, .camera),
            (.microphone, .voice)
        ]
        for (kind, lane) in overlapping {
            XCTAssertEqual(kind.title, lane.title, "\(kind) title disagrees with \(lane)")
            XCTAssertEqual(kind.symbol, lane.symbol, "\(kind) symbol disagrees with \(lane)")
        }
    }

    func testSystemAudioTitleAndSymbolAgreeWithTimelineLane() {
        XCTAssertEqual(TrackKind.systemAudio.title, TimelineLane.systemAudio.title)
        XCTAssertEqual(TrackKind.systemAudio.symbol, TimelineLane.systemAudio.symbol)
    }

    /// `TrackKind`'s raw values are also what `events.jsonl` writes as `track_start` labels —
    /// changing one silently breaks reading offsets back out of old session logs.
    func testRawValuesMatchWhatEventsJSONLAlreadyWrites() {
        XCTAssertEqual(TrackKind.screen.rawValue, "screen")
        XCTAssertEqual(TrackKind.camera.rawValue, "camera")
        XCTAssertEqual(TrackKind.microphone.rawValue, "microphone")
        XCTAssertEqual(TrackKind.systemAudio.rawValue, "systemAudio")
    }

    func testCodableRoundTrip() throws {
        let data = try JSONEncoder().encode(TrackKind.allCases)
        let decoded = try JSONDecoder().decode([TrackKind].self, from: data)
        XCTAssertEqual(decoded, TrackKind.allCases)
    }
}
