import XCTest
@testable import Aura

final class RecordingManifestTests: XCTestCase {
    private func tempURL() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("\(UUID().uuidString).json")
    }

    func testWriteThenLoadRoundTrips() throws {
        let url = tempURL()
        defer { try? FileManager.default.removeItem(at: url) }

        let manifest = RecordingManifest(
            profile: RecordingProfile(tracks: [.microphone]),
            startedAt: Date(timeIntervalSince1970: 1_700_000_000),
            microphoneName: "Shure MV7"
        )
        try manifest.write(to: url)

        XCTAssertEqual(RecordingManifest.load(from: url), manifest)
    }

    func testLoadToleratesUnknownExtraKeys() throws {
        let url = tempURL()
        defer { try? FileManager.default.removeItem(at: url) }

        let json = """
        {
          "schemaVersion": 1,
          "profile": { "tracks": ["screen", "microphone"] },
          "startedAt": "2026-01-01T00:00:00Z",
          "somethingFromTheFuture": "ignored"
        }
        """
        try json.data(using: .utf8)!.write(to: url)

        let loaded = RecordingManifest.load(from: url)
        XCTAssertEqual(loaded?.profile.tracks, [.screen, .microphone])
    }

    func testLoadIsNilForAMissingFile() {
        XCTAssertNil(RecordingManifest.load(from: tempURL()))
    }

    func testLoadIsNilForMalformedJSON() throws {
        let url = tempURL()
        defer { try? FileManager.default.removeItem(at: url) }
        try Data("not json".utf8).write(to: url)

        XCTAssertNil(RecordingManifest.load(from: url))
    }
}
