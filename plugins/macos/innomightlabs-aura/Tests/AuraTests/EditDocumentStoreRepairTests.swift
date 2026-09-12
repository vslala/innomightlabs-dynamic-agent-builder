import XCTest
@testable import Aura

/// `repair` has two independent commit conditions, and conflating them caused a real bug: the
/// transcript-identity stamp was gated on "did a word cut's span move", so on every document
/// whose spans were already correct the stamp was thrown away — leaving the re-transcription
/// guard permanently disarmed.
@MainActor
final class EditDocumentStoreRepairTests: XCTestCase {
    private func store(_ document: SessionEdit = .initial(duration: 60)) -> EditDocumentStore {
        EditDocumentStore(
            document: document,
            fileURL: URL(fileURLWithPath: NSTemporaryDirectory())
                .appendingPathComponent("repair-\(UUID().uuidString).json")
        )
    }

    func testReturningFalseDiscardsEveryChangeTheClosureMade() {
        let store = self.store()

        store.repair { document in
            document.transcriptIdentity = "w10-abc"
            return false
        }

        XCTAssertNil(
            store.document.transcriptIdentity,
            "a false return discards the whole transform, not just part of it"
        )
    }

    func testReturningTrueCommitsAnIdentityOnlyChange() {
        let store = self.store()

        store.repair { document in
            document.transcriptIdentity = "w10-abc"
            return true
        }

        XCTAssertEqual(store.document.transcriptIdentity, "w10-abc")
    }

    /// Why returning `true` unconditionally is safe: the store still drops a transform that
    /// changed nothing, so there is no spurious save to guard against.
    func testATrueReturnThatChangesNothingIsStillDropped() {
        let original = SessionEdit.initial(duration: 60)
        let store = self.store(original)

        store.repair { _ in true }

        XCTAssertEqual(store.document, original)
    }

    func testRepairDoesNotConsumeUndoHistory() {
        let store = self.store()
        XCTAssertFalse(store.canUndo)

        store.repair { document in
            document.transcriptIdentity = "w10-abc"
            return true
        }

        // The user never asked for a repair, so it must not be something they can undo into.
        XCTAssertFalse(store.canUndo, "a repair must not enter the undo stack")
    }
}
