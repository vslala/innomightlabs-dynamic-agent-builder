import XCTest
@testable import Aura

final class EventLogWriterTests: XCTestCase {
    private var fileURL: URL!

    override func setUpWithError() throws {
        fileURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("jsonl")
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: fileURL)
    }

    func testEachEventIsOneRoundTrippableLine() throws {
        let writer = try EventLogWriter(fileURL: fileURL)
        try writer.append(RecordingEvent(ts: 0, type: .recordStart, app: "Chrome"))
        try writer.append(RecordingEvent(ts: 18.3, type: .pause, app: nil))
        try writer.append(RecordingEvent(ts: 21.1, type: .resume, app: nil))
        try writer.append(RecordingEvent(ts: 42.0, type: .recordStop, app: nil))
        writer.close()

        let contents = try String(contentsOf: fileURL, encoding: .utf8)
        let lines = contents.split(separator: "\n", omittingEmptySubsequences: true)
        XCTAssertEqual(lines.count, 4)

        let decoder = JSONDecoder()
        struct DecodedEvent: Decodable { let ts: Double; let type: String; let app: String? }
        let decoded = try lines.map { try decoder.decode(DecodedEvent.self, from: Data($0.utf8)) }

        XCTAssertEqual(decoded.map(\.type), ["record_start", "pause", "resume", "record_stop"])
        XCTAssertEqual(decoded[0].app, "Chrome")
    }

    func testOptionalFieldOmittedWhenNil() throws {
        let writer = try EventLogWriter(fileURL: fileURL)
        try writer.append(RecordingEvent(ts: 1, type: .pause, app: nil))
        writer.close()

        let contents = try String(contentsOf: fileURL, encoding: .utf8)
        XCTAssertFalse(contents.contains("\"app\""))
    }

    func testFileSizeGrowsMonotonically() throws {
        let writer = try EventLogWriter(fileURL: fileURL)
        var previousSize: UInt64 = 0

        for index in 0..<5 {
            try writer.append(RecordingEvent(ts: Double(index), type: .pause, app: nil))
            let attributes = try FileManager.default.attributesOfItem(atPath: fileURL.path)
            let size = attributes[.size] as? UInt64 ?? 0
            XCTAssertGreaterThan(size, previousSize)
            previousSize = size
        }
        writer.close()
    }
}
