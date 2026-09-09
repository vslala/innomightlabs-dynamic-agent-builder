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
    }

    func testRootURLNestedUnderBaseDirectory() {
        let folder = SessionFolder.make(date: fixedDate, suffix: "ab12", baseDirectory: baseDirectory)
        XCTAssertEqual(folder.rootURL.deletingLastPathComponent(), baseDirectory)
    }
}
