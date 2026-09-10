import XCTest
@testable import Aura

@MainActor
final class EditDocumentStoreTests: XCTestCase {
    private var folder: SessionFolder!

    override func setUpWithError() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-edit-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        folder = SessionFolder.load(rootURL: root)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: folder.rootURL)
    }

    private func store(duration: TimeInterval = 30) -> EditDocumentStore {
        EditDocumentStore.load(folder: folder, duration: duration, micTimeOffset: 0)
    }

    func testLoadWithNothingOnDiskStartsFromAFreshDocument() {
        let store = self.store()

        XCTAssertEqual(store.document.duration, 30)
        XCTAssertFalse(store.canUndo)
    }

    func testAppliedOperationUpdatesTheDocument() {
        let store = self.store()

        XCTAssertTrue(store.apply(.removeRange(TimeSpan(start: 10, end: 15))))
        XCTAssertEqual(store.document.duration, 25)
        XCTAssertNil(store.lastError)
    }

    func testRejectedOperationLeavesTheDocumentAloneAndReportsWhy() {
        let store = self.store()
        let before = store.document

        XCTAssertFalse(store.apply(.removeRange(TimeSpan(start: 0, end: 30))))
        XCTAssertEqual(store.document, before)
        XCTAssertEqual(store.lastError, .wouldRemoveEntireTimeline)
        XCTAssertFalse(store.canUndo, "A rejected operation must not create an undo step")
    }

    func testUndoAndRedoRoundTrip() {
        let store = self.store()
        let original = store.document

        store.apply(.removeRange(TimeSpan(start: 10, end: 15)))
        let edited = store.document

        XCTAssertTrue(store.canUndo)
        store.undo()
        XCTAssertEqual(store.document, original)

        XCTAssertTrue(store.canRedo)
        store.redo()
        XCTAssertEqual(store.document, edited)
    }

    func testApplyingAfterUndoDiscardsTheRedoStack() {
        let store = self.store()

        store.apply(.removeRange(TimeSpan(start: 10, end: 15)))
        store.undo()
        XCTAssertTrue(store.canRedo)

        store.apply(.setLaneMuted(lane: .microphone, muted: true))
        XCTAssertFalse(store.canRedo)
    }

    func testUndoAtTheBeginningIsANoOp() {
        let store = self.store()
        let original = store.document

        store.undo()

        XCTAssertEqual(store.document, original)
    }

    func testBatchAppliesAsOneUndoStep() {
        let store = self.store()
        let original = store.document

        XCTAssertTrue(store.apply([
            .removeRange(TimeSpan(start: 10, end: 12)),
            .setLaneMuted(lane: .systemAudio, muted: true)
        ]))
        store.undo()

        XCTAssertEqual(store.document, original)
    }

    func testBatchIsAllOrNothing() {
        // A half-applied set of agent suggestions would be worse than none.
        let store = self.store()
        let original = store.document

        XCTAssertFalse(store.apply([
            .removeRange(TimeSpan(start: 10, end: 12)),
            .removeRange(TimeSpan(start: 0, end: 30))
        ]))
        XCTAssertEqual(store.document, original)
        XCTAssertFalse(store.canUndo)
    }

    func testFlushPersistsAndReloads() throws {
        let store = self.store()
        store.apply(.removeRange(TimeSpan(start: 10, end: 15)))
        store.apply(.setLaneMuted(lane: .systemAudio, muted: true))
        store.flush()

        XCTAssertTrue(FileManager.default.fileExists(atPath: folder.editURL.path))

        let reloaded = self.store()
        XCTAssertEqual(reloaded.document, store.document)
        XCTAssertEqual(reloaded.document.duration, 25)
    }

    func testUnreadableDocumentFallsBackToAFreshOne() throws {
        try Data("not json".utf8).write(to: folder.editURL)

        XCTAssertEqual(store().document.duration, 30)
    }

    func testDocumentFromANewerSchemaIsIgnored() throws {
        var future = SessionEdit.initial(duration: 99)
        future.schemaVersion = SessionEdit.currentSchemaVersion + 1
        try JSONEncoder().encode(future).write(to: folder.editURL)

        XCTAssertEqual(store().document.duration, 30, "A newer schema should not be half-read")
    }
}
