import Foundation

final class SessionManager {
    let folder: SessionFolder
    private(set) var eventLogWriter: EventLogWriter?

    init(baseDirectory: URL = SessionFolder.defaultBaseDirectory) {
        folder = SessionFolder.make(
            date: Date(),
            suffix: SessionFolder.randomSuffix(),
            baseDirectory: baseDirectory
        )
    }

    func createSessionDirectory() throws {
        try FileManager.default.createDirectory(
            at: folder.rootURL,
            withIntermediateDirectories: true
        )
        try FileManager.default.createDirectory(
            at: folder.screenshotsURL,
            withIntermediateDirectories: true
        )
        eventLogWriter = try EventLogWriter(fileURL: folder.eventsURL)
    }

    func logEvent(_ event: RecordingEvent) {
        try? eventLogWriter?.append(event)
    }

    func writeManifest(_ manifest: RecordingManifest) throws {
        try manifest.write(to: folder.manifestURL)
    }

    func close() {
        eventLogWriter?.close()
    }
}
