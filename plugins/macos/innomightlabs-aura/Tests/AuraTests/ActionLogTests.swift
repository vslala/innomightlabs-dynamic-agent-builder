import XCTest
@testable import Aura

@MainActor
final class ActionLogTests: XCTestCase {
    private func folder() throws -> SessionFolder {
        let folder = SessionFolder.make(date: Date(), suffix: UUID().uuidString,
            baseDirectory: FileManager.default.temporaryDirectory.appendingPathComponent("aura-action-log-tests"))
        try FileManager.default.createDirectory(at: folder.rootURL, withIntermediateDirectories: true)
        return folder
    }

    func testDurableJournalAndAtomicSnapshotRoundTrip() throws {
        let folder = try folder()
        defer { try? FileManager.default.removeItem(at: folder.rootURL) }
        let writer = try ActionLogWriter(folder: folder)
        let entries: [ActionLog.Entry] = [
            .init(t: 0, stepID: "a", kind: .stepStart),
            .init(t: 0.25, stepID: "a", kind: .mouseDown, point: CGPoint(x: 2, y: 4)),
            .init(t: 0.5, stepID: "a", kind: .stepEnd, rect: CGRect(x: 1, y: 2, width: 30, height: 40))
        ]
        for entry in entries { try writer.append(entry) }
        // The journal is recoverable before closing the writer or finishing the take.
        XCTAssertEqual(try ActionLog.recoverJournal(from: folder.actionLogJournalURL).entries, entries)
        writer.close()
        try ActionLog.finalizeJournal(in: folder)
        XCTAssertEqual(try JSONDecoder().decode(ActionLog.self, from: Data(contentsOf: folder.actionLogURL)).entries, entries)
        XCTAssertTrue(FileManager.default.fileExists(atPath: folder.actionLogJournalURL.path))
    }

    func testCrashTruncatedLastLineIsDiscardedBeforeAppending() throws {
        let folder = try folder()
        defer { try? FileManager.default.removeItem(at: folder.rootURL) }
        let first = ActionLog.Entry(t: 1, stepID: "first", kind: .stepStart)
        var bytes = try JSONEncoder().encode(first)
        bytes.append(contentsOf: Data("\n{\"t\":2".utf8))
        try bytes.write(to: folder.actionLogJournalURL)
        XCTAssertEqual(try ActionLog.recoverJournal(from: folder.actionLogJournalURL).entries, [first])
        let writer = try ActionLogWriter(folder: folder)
        let second = ActionLog.Entry(t: 2, stepID: "first", kind: .stepEnd)
        try writer.append(second)
        writer.close()
        XCTAssertEqual(try ActionLog.recoverJournal(from: folder.actionLogJournalURL).entries, [first, second])
    }

    func testRejectsNonFiniteAndBackwardsSessionTime() throws {
        let folder = try folder()
        defer { try? FileManager.default.removeItem(at: folder.rootURL) }
        let writer = try ActionLogWriter(folder: folder)
        defer { writer.close() }
        try writer.append(.init(t: 3, stepID: "step", kind: .stepStart))
        XCTAssertThrowsError(try writer.append(.init(t: 2, stepID: "step", kind: .stepEnd)))
        XCTAssertThrowsError(try writer.append(.init(t: .nan, stepID: "step", kind: .stepEnd)))
        XCTAssertThrowsError(try writer.append(.init(t: .infinity, stepID: "step", kind: .stepEnd)))
    }

    func testBrowserManifestAndBrowserStepAreBackwardCompatible() throws {
        let folder = try folder()
        defer { try? FileManager.default.removeItem(at: folder.rootURL) }
        var manifest = RecordingManifest(profile: RecordingProfile(tracks: [.screen]), startedAt: Date(timeIntervalSince1970: 100))
        try manifest.write(to: folder.manifestURL)
        XCTAssertNil(RecordingManifest.load(from: folder.manifestURL)?.browserTake)
        manifest.browserTake = BrowserTakeMetadata(specID: UUID(), revision: 7, status: .failed, failureReason: "viewportResized")
        try manifest.write(to: folder.manifestURL)
        XCTAssertEqual(RecordingManifest.load(from: folder.manifestURL), manifest)
        let event = RecordingEvent(ts: 20, type: .browserStep, mediaTs: 5, label: "Open dashboard")
        XCTAssertEqual(try JSONDecoder().decode(RecordingEvent.self, from: JSONEncoder().encode(event)), event)
        XCTAssertEqual(EventTimeline(events: [event]).entries[0].mediaTs, 5)
        XCTAssertEqual(EventTimeline(events: [event]).markers.map(\.event), [event])
    }

    func testCursorPreferenceSurvivesProfileReplacementAndDefaultIsVisible() {
        let original = RecordingRequest(profile: RecordingProfile(tracks: [.microphone]))
        XCTAssertFalse(original.hidesSystemCursor)
        var browser = original
        browser.hidesSystemCursor = true
        browser.browserTake = BrowserTakeMetadata(specID: UUID(), revision: 1)
        let replaced = browser.replacing(profile: RecordingProfile(tracks: [.screen]))
        XCTAssertTrue(replaced.hidesSystemCursor)
        XCTAssertEqual(replaced.browserTake, browser.browserTake)
    }
}
