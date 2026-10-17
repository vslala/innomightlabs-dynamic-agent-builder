import Foundation
import CoreGraphics

/// Recorded facts only. Input values, URLs, snapshots and credential handover events never belong here.
struct ActionLog: Codable, Equatable, Sendable {
    struct Entry: Codable, Equatable, Sendable {
        enum Kind: String, Codable, Sendable {
            case stepStart, mouseMove, mouseDown, mouseUp, typed, stepEnd
        }
        let t: TimeInterval
        let stepID: String
        let kind: Kind
        var point: CGPoint? = nil
        var rect: CGRect? = nil
    }
    let entries: [Entry]

    /// A killed process can leave an incomplete last line. Recover only the durable prefix;
    /// never skip a corrupt middle line and make a later action look continuous with it.
    static func recoverJournal(from url: URL) throws -> ActionLog {
        let data = try Data(contentsOf: url)
        let decoder = JSONDecoder()
        var entries: [Entry] = []
        var start = data.startIndex
        while let newline = data[start...].firstIndex(of: 10) {
            guard let entry = try? decoder.decode(Entry.self, from: data[start..<newline]),
                  entry.t.isFinite, entry.t >= (entries.last?.t ?? 0) else { break }
            entries.append(entry)
            start = data.index(after: newline)
        }
        return ActionLog(entries: entries)
    }

    static func finalizeJournal(in folder: SessionFolder) throws {
        let log = try recoverJournal(from: folder.actionLogJournalURL)
        try JSONEncoder().encode(log).write(to: folder.actionLogURL, options: .atomic)
        // Keep the journal: it is the recovery source if finalization itself is interrupted.
    }
}

enum ActionLogError: Error, LocalizedError {
    case invalidSessionTime
    var errorDescription: String? { "Browser action times must be finite, nonnegative and in session order." }
}

/// Main-actor serialization preserves event order. Each complete line is flushed before the
/// next action can run; the atomic JSON snapshot is produced before recording completion.
@MainActor
final class ActionLogWriter {
    private let handle: FileHandle
    private var lastTime: TimeInterval = 0

    init(folder: SessionFolder) throws {
        if !FileManager.default.fileExists(atPath: folder.actionLogJournalURL.path) {
            try Data().write(to: folder.actionLogJournalURL, options: .atomic)
        }
        let recovered = try ActionLog.recoverJournal(from: folder.actionLogJournalURL)
        lastTime = recovered.entries.last?.t ?? 0
        handle = try FileHandle(forWritingTo: folder.actionLogJournalURL)
        // Remove a crash-truncated suffix before appending, rather than joining two JSON lines.
        let encoder = JSONEncoder()
        var prefix = Data()
        for entry in recovered.entries {
            prefix.append(try encoder.encode(entry)); prefix.append(10)
        }
        try handle.truncate(atOffset: 0)
        try handle.write(contentsOf: prefix)
        try handle.synchronize()
    }

    func append(_ entry: ActionLog.Entry) throws {
        guard entry.t.isFinite, entry.t >= lastTime else {
            throw ActionLogError.invalidSessionTime
        }
        var data = try JSONEncoder().encode(entry)
        data.append(10)
        try handle.write(contentsOf: data)
        try handle.synchronize()
        lastTime = entry.t
    }

    func close() { try? handle.close() }
    deinit { try? handle.close() }
}
