import XCTest
@testable import Aura

final class SessionFolderTests: XCTestCase {
    private let fixedDate = Date(timeIntervalSince1970: 1_700_000_000) // 2023-11-14 22:13:20 UTC
    private let baseDirectory = URL(fileURLWithPath: "/tmp/aura-tests", isDirectory: true)

    func testIDFormat() {
        let id = SessionFolder.makeID(date: fixedDate, suffix: "ab12")
        XCTAssertTrue(id.hasSuffix("-ab12"))
        XCTAssertEqual(id.split(separator: "-").count, 3)
    }

    func testDifferentSuffixesDoNotCollide() {
        let folderA = SessionFolder.make(date: fixedDate, suffix: "aaaa", baseDirectory: baseDirectory)
        let folderB = SessionFolder.make(date: fixedDate, suffix: "bbbb", baseDirectory: baseDirectory)
        XCTAssertNotEqual(folderA.id, folderB.id)
        XCTAssertNotEqual(folderA.rootURL, folderB.rootURL)
    }

    func testDerivedFileURLs() {
        let folder = SessionFolder.make(date: fixedDate, suffix: "ab12", baseDirectory: baseDirectory)

        XCTAssertEqual(folder.screenURL, folder.rootURL.appendingPathComponent("screen.mov"))
        XCTAssertEqual(folder.cameraURL, folder.rootURL.appendingPathComponent("camera.mov"))
        XCTAssertEqual(folder.microphoneURL, folder.rootURL.appendingPathComponent("microphone.m4a"))
        XCTAssertEqual(folder.systemAudioURL, folder.rootURL.appendingPathComponent("system-audio.m4a"))
        XCTAssertEqual(folder.screenshotsURL, folder.rootURL.appendingPathComponent("screenshots", isDirectory: true))
        XCTAssertEqual(folder.eventsURL, folder.rootURL.appendingPathComponent("events.jsonl"))
        XCTAssertEqual(folder.transcriptURL, folder.rootURL.appendingPathComponent("transcript.json"))
        XCTAssertEqual(folder.editURL, folder.rootURL.appendingPathComponent("edit.json"))
        XCTAssertEqual(folder.manifestURL, folder.rootURL.appendingPathComponent("recording.json"))
    }

    func testPeakCachesSitBesideTheAudioTheyDescribe() {
        let folder = SessionFolder.make(date: fixedDate, suffix: "ab12", baseDirectory: baseDirectory)

        XCTAssertEqual(folder.microphonePeaksURL, folder.rootURL.appendingPathComponent("microphone.peaks"))
        XCTAssertEqual(folder.systemAudioPeaksURL, folder.rootURL.appendingPathComponent("system-audio.peaks"))
    }

    func testLoadDerivesTheSameURLsAsMake() {
        let made = SessionFolder.make(date: fixedDate, suffix: "ab12", baseDirectory: baseDirectory)
        let loaded = SessionFolder.load(rootURL: made.rootURL)

        XCTAssertEqual(loaded.id, made.id)
        XCTAssertEqual(loaded.rootURL, made.rootURL)
        XCTAssertEqual(loaded.screenURL, made.screenURL)
        XCTAssertEqual(loaded.cameraURL, made.cameraURL)
        XCTAssertEqual(loaded.microphoneURL, made.microphoneURL)
        XCTAssertEqual(loaded.systemAudioURL, made.systemAudioURL)
        XCTAssertEqual(loaded.screenshotsURL, made.screenshotsURL)
        XCTAssertEqual(loaded.eventsURL, made.eventsURL)
        XCTAssertEqual(loaded.transcriptURL, made.transcriptURL)
        XCTAssertEqual(loaded.editURL, made.editURL)
        XCTAssertEqual(loaded.manifestURL, made.manifestURL)
        XCTAssertEqual(loaded.microphonePeaksURL, made.microphonePeaksURL)
        XCTAssertEqual(loaded.systemAudioPeaksURL, made.systemAudioPeaksURL)
    }

    func testExistingSessionsListsOnlyRealSessionsNewestFirst() throws {
        let base = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-sessions-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: base) }

        for id in ["20260101-120000-aaaa", "20260202-120000-bbbb"] {
            let root = base.appendingPathComponent(id, isDirectory: true)
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
            try Data().write(to: root.appendingPathComponent("events.jsonl"))
        }
        // An unrelated folder, and a session directory with no event log: neither is
        // openable, so neither should be offered.
        try FileManager.default.createDirectory(
            at: base.appendingPathComponent("Screenshots", isDirectory: true),
            withIntermediateDirectories: true
        )
        try FileManager.default.createDirectory(
            at: base.appendingPathComponent("20260303-120000-cccc", isDirectory: true),
            withIntermediateDirectories: true
        )
        try Data().write(to: base.appendingPathComponent("stray.txt"))

        let sessions = SessionFolder.existingSessions(in: base)

        XCTAssertEqual(sessions.map(\.id), ["20260202-120000-bbbb", "20260101-120000-aaaa"])
    }

    func testExistingSessionsIsEmptyWhenTheDirectoryIsAbsent() {
        let missing = FileManager.default.temporaryDirectory
            .appendingPathComponent("absent-\(UUID().uuidString)", isDirectory: true)

        XCTAssertTrue(SessionFolder.existingSessions(in: missing).isEmpty)
    }

    func testRootURLNestedUnderBaseDirectory() {
        let folder = SessionFolder.make(date: fixedDate, suffix: "ab12", baseDirectory: baseDirectory)
        XCTAssertEqual(folder.rootURL.deletingLastPathComponent(), baseDirectory)
    }

    // MARK: - Segments

    /// Window 0 must keep the unsegmented name for every kind, which is what makes a session
    /// that never switches profiles byte-identical to one recorded before segmenting existed.
    func testWindowZeroKeepsTheLegacyFileName() {
        XCTAssertEqual(SessionFolder.fileName(for: .screen, segment: 0), "screen.mov")
        XCTAssertEqual(SessionFolder.fileName(for: .camera, segment: 0), "camera.mov")
        XCTAssertEqual(SessionFolder.fileName(for: .microphone, segment: 0), "microphone.m4a")
        XCTAssertEqual(SessionFolder.fileName(for: .systemAudio, segment: 0), "system-audio.m4a")
    }

    func testLaterSegmentsAreSuffixed() {
        XCTAssertEqual(SessionFolder.fileName(for: .screen, segment: 1), "screen-1.mov")
        XCTAssertEqual(SessionFolder.fileName(for: .systemAudio, segment: 2), "system-audio-2.m4a")
    }

    func testURLForSegmentIsRootedUnderTheSessionFolder() {
        let folder = SessionFolder.make(date: fixedDate, suffix: "ab12", baseDirectory: baseDirectory)
        XCTAssertEqual(folder.url(for: .screen, segment: 0), folder.screenURL)
        XCTAssertEqual(
            folder.url(for: .screen, segment: 1),
            folder.rootURL.appendingPathComponent("screen-1.mov")
        )
    }

    func testSegmentURLsDiscoversAndSortsExistingSegments() throws {
        let base = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-segments-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: base) }

        let folder = SessionFolder.make(date: fixedDate, suffix: "ab12", baseDirectory: base)
        try FileManager.default.createDirectory(at: folder.rootURL, withIntermediateDirectories: true)

        // Out of order on disk, plus a screenshot directory and a camera file that must not be
        // mistaken for a screen segment despite the shared "screen" prefix.
        for name in ["screen-2.mov", "screen.mov", "screen-1.mov", "camera.mov"] {
            try Data().write(to: folder.rootURL.appendingPathComponent(name))
        }
        try FileManager.default.createDirectory(
            at: folder.rootURL.appendingPathComponent("screenshots", isDirectory: true),
            withIntermediateDirectories: true
        )

        let segments = folder.segmentURLs(for: .screen)

        XCTAssertEqual(segments.map(\.lastPathComponent), ["screen.mov", "screen-1.mov", "screen-2.mov"])
    }

    func testSegmentURLsIsEmptyWhenNothingWasEverRecordedForThatKind() {
        let folder = SessionFolder.make(date: fixedDate, suffix: "ab12", baseDirectory: baseDirectory)
        XCTAssertTrue(folder.segmentURLs(for: .systemAudio).isEmpty)
    }
}
