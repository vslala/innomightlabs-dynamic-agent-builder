import Foundation

/// Owns the `SessionEdit` for one review window and is the only thing that mutates it.
///
/// Every change goes through `apply`, whether it came from a drag in the UI, the agent, or a
/// voice command — so undo, persistence, and validation are written once and every source of
/// edits gets them. Undo is snapshot-based: the document is a handful of small arrays, so
/// keeping whole copies is cheaper to reason about than inverting each operation.
@MainActor
final class EditDocumentStore: ObservableObject {
    @Published private(set) var document: SessionEdit
    /// Set when an operation was rejected. Surfaced rather than swallowed, because a
    /// rejected agent suggestion is something the user needs to see.
    @Published var lastError: EditOperationError?

    private let fileURL: URL
    private var undoStack: [SessionEdit] = []
    private var redoStack: [SessionEdit] = []
    private var pendingSave: Task<Void, Never>?

    private static let saveDebounce = Duration.milliseconds(400)

    var canUndo: Bool { !undoStack.isEmpty }
    var canRedo: Bool { !redoStack.isEmpty }

    init(document: SessionEdit, fileURL: URL) {
        self.document = document
        self.fileURL = fileURL
    }

    /// Reopens a session's edit document, migrating an older schema and falling back to a
    /// fresh one when there is nothing on disk, it is unreadable, or it came from a newer
    /// build.
    static func load(
        folder: SessionFolder,
        duration: TimeInterval,
        micTimeOffset: TimeInterval
    ) -> EditDocumentStore {
        let fallback = SessionEdit.initial(duration: duration, micTimeOffset: micTimeOffset)

        guard let data = try? Data(contentsOf: folder.editURL) else {
            return EditDocumentStore(document: fallback, fileURL: folder.editURL)
        }

        switch SessionEditMigration.decode(data, recordingDuration: duration) {
        case .current(let document):
            return EditDocumentStore(document: document, fileURL: folder.editURL)

        case .migrated(let document):
            // Keep the original before anything overwrites it. `repair` schedules a save
            // within 400ms of the window opening, so without this the only copy of the old
            // format is gone before the user has done anything — and rolling a build back
            // would then mean losing their edits.
            let backup = folder.editURL.appendingPathExtension("v1.bak")
            if !FileManager.default.fileExists(atPath: backup.path) {
                try? data.write(to: backup, options: .atomic)
            }
            return EditDocumentStore(document: document, fileURL: folder.editURL)

        case .unreadable, .tooNew:
            return EditDocumentStore(document: fallback, fileURL: folder.editURL)
        }
    }

    @discardableResult
    func apply(_ operation: EditOperation) -> Bool {
        do {
            let updated = try document.applying(operation)
            // An operation that changes nothing must not consume an undo step, or the user
            // presses undo and apparently nothing happens.
            guard updated != document else { return true }
            undoStack.append(document)
            redoStack.removeAll()
            document = updated
            lastError = nil
            scheduleSave()
            return true
        } catch let error as EditOperationError {
            lastError = error
            return false
        } catch {
            return false
        }
    }

    /// Applies a batch as one undo step, and only if every operation succeeds — a partially
    /// applied set of agent suggestions would be worse than none.
    @discardableResult
    func apply(_ operations: [EditOperation]) -> Bool {
        guard !operations.isEmpty else { return false }

        do {
            let updated = try operations.reduce(document) { try $0.applying($1) }
            guard updated != document else { return true }
            undoStack.append(document)
            redoStack.removeAll()
            document = updated
            lastError = nil
            scheduleSave()
            return true
        } catch let error as EditOperationError {
            lastError = error
            return false
        } catch {
            return false
        }
    }

    /// Corrects derived data in place, without an undo step.
    ///
    /// For repairs rather than edits: the user never asked for it, so it should not consume
    /// their undo history or be something they can accidentally undo into a broken state.
    func repair(_ transform: (inout SessionEdit) -> Bool) {
        var updated = document
        guard transform(&updated), updated != document else { return }
        document = updated
        scheduleSave()
    }

    func undo() {
        guard let previous = undoStack.popLast() else { return }
        redoStack.append(document)
        document = previous
        scheduleSave()
    }

    func redo() {
        guard let next = redoStack.popLast() else { return }
        undoStack.append(document)
        document = next
        scheduleSave()
    }

    /// Writes immediately, cancelling any debounced write. Call before the window closes.
    func flush() {
        pendingSave?.cancel()
        pendingSave = nil
        write(document)
    }

    private func scheduleSave() {
        pendingSave?.cancel()
        let snapshot = document
        pendingSave = Task { [weak self] in
            try? await Task.sleep(for: Self.saveDebounce)
            guard !Task.isCancelled else { return }
            self?.write(snapshot)
        }
    }

    private func write(_ document: SessionEdit) {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard let data = try? encoder.encode(document) else { return }
        try? data.write(to: fileURL, options: .atomic)
    }
}
