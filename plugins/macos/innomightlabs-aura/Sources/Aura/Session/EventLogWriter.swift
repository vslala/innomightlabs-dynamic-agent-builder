import Foundation

final class EventLogWriter {
    private let fileHandle: FileHandle
    private let encoder = JSONEncoder()

    init(fileURL: URL) throws {
        if !FileManager.default.fileExists(atPath: fileURL.path) {
            FileManager.default.createFile(atPath: fileURL.path, contents: nil)
        }
        fileHandle = try FileHandle(forWritingTo: fileURL)
        fileHandle.seekToEndOfFile()
    }

    func append(_ event: RecordingEvent) throws {
        var data = try encoder.encode(event)
        data.append(0x0A)
        fileHandle.write(data)
    }

    func close() {
        try? fileHandle.close()
    }
}
