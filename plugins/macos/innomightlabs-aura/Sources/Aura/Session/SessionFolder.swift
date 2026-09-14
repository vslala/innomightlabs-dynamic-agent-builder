import Foundation

struct SessionFolder {
    let id: String
    let rootURL: URL
    let screenURL: URL
    let cameraURL: URL
    let microphoneURL: URL
    let systemAudioURL: URL
    let screenshotsURL: URL
    let eventsURL: URL
    let transcriptURL: URL
    let editURL: URL
    /// The compact session description sent to the agent, kept so a suggestion can always be
    /// traced back to exactly what the agent was told.
    let digestURL: URL
    /// What the user asked to record. Absent for sessions recorded before Phase 6 — see
    /// `RecordingManifest` for why nothing downstream may depend on this file existing.
    let manifestURL: URL

    /// Waveform peak caches sit beside the audio file they describe, so the review
    /// layer never has to rebuild a path to find one.
    var microphonePeaksURL: URL { Self.peaksURL(for: microphoneURL) }
    var systemAudioPeaksURL: URL { Self.peaksURL(for: systemAudioURL) }

    /// Thumbnail caches, beside the video they describe, for the same reason.
    var screenFilmstripURL: URL { Self.filmstripURL(for: screenURL) }
    var cameraFilmstripURL: URL { Self.filmstripURL(for: cameraURL) }

    static func filmstripURL(for source: URL) -> URL {
        source.deletingPathExtension().appendingPathExtension("filmstrip")
    }

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
        return SessionFolder(rootURL: baseDirectory.appendingPathComponent(id, isDirectory: true), id: id)
    }

    /// Reopens an existing session directory, deriving exactly the same filenames `make`
    /// produced. The session id is the folder name, so a folder is self-describing and
    /// nothing about a past session needs to be recorded elsewhere.
    static func load(rootURL: URL) -> SessionFolder {
        SessionFolder(rootURL: rootURL, id: rootURL.lastPathComponent)
    }

    private init(rootURL: URL, id: String) {
        self.id = id
        self.rootURL = rootURL
        screenURL = rootURL.appendingPathComponent("screen.mov")
        cameraURL = rootURL.appendingPathComponent("camera.mov")
        microphoneURL = rootURL.appendingPathComponent("microphone.m4a")
        systemAudioURL = rootURL.appendingPathComponent("system-audio.m4a")
        screenshotsURL = rootURL.appendingPathComponent("screenshots", isDirectory: true)
        eventsURL = rootURL.appendingPathComponent("events.jsonl")
        transcriptURL = rootURL.appendingPathComponent("transcript.json")
        editURL = rootURL.appendingPathComponent("edit.json")
        digestURL = rootURL.appendingPathComponent("digest.json")
        manifestURL = rootURL.appendingPathComponent("recording.json")
    }

    private static func peaksURL(for audioURL: URL) -> URL {
        audioURL.deletingPathExtension().appendingPathExtension("peaks")
    }

    static var defaultBaseDirectory: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Movies", isDirectory: true)
            .appendingPathComponent("Aura", isDirectory: true)
    }

    /// Existing session directories, newest first. Session ids are timestamp-prefixed, so a
    /// reverse lexicographic sort is a chronological sort.
    ///
    /// A directory counts as a session only if it has an `events.jsonl`, which every session
    /// gets at creation — otherwise any unrelated folder under `~/Movies/Aura` would be
    /// offered for opening and then fail with "no readable media".
    static func existingSessions(in baseDirectory: URL = defaultBaseDirectory) -> [SessionFolder] {
        let names = (try? FileManager.default.contentsOfDirectory(atPath: baseDirectory.path)) ?? []

        return names
            .sorted(by: >)
            .map { load(rootURL: baseDirectory.appendingPathComponent($0, isDirectory: true)) }
            .filter { FileManager.default.fileExists(atPath: $0.eventsURL.path) }
    }
}
