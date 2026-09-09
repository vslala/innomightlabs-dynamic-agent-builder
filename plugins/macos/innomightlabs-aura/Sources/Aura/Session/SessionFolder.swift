import Foundation

struct SessionFolder {
    let id: String
    let rootURL: URL
    let screenURL: URL
    let cameraURL: URL
    let microphoneURL: URL
    let systemAudioURL: URL
    let eventsURL: URL

    private static let idFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        formatter.timeZone = TimeZone.current
        return formatter
    }()

    static func makeID(date: Date, suffix: String) -> String {
        "\(idFormatter.string(from: date))-\(suffix)"
    }

    static func randomSuffix() -> String {
        String(format: "%04x", UInt16.random(in: 0...UInt16.max))
    }

    static func make(date: Date, suffix: String, baseDirectory: URL) -> SessionFolder {
        let id = makeID(date: date, suffix: suffix)
        let root = baseDirectory.appendingPathComponent(id, isDirectory: true)
        return SessionFolder(
            id: id,
            rootURL: root,
            screenURL: root.appendingPathComponent("screen.mov"),
            cameraURL: root.appendingPathComponent("camera.mov"),
            microphoneURL: root.appendingPathComponent("microphone.m4a"),
            systemAudioURL: root.appendingPathComponent("system-audio.m4a"),
            eventsURL: root.appendingPathComponent("events.jsonl")
        )
    }

    static var defaultBaseDirectory: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Movies", isDirectory: true)
            .appendingPathComponent("Aura", isDirectory: true)
    }
}
