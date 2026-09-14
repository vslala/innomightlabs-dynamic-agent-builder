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
        screenURL = rootURL.appendingPathComponent(Self.fileName(for: .screen, segment: 0))
        cameraURL = rootURL.appendingPathComponent(Self.fileName(for: .camera, segment: 0))
        microphoneURL = rootURL.appendingPathComponent(Self.fileName(for: .microphone, segment: 0))
        systemAudioURL = rootURL.appendingPathComponent(Self.fileName(for: .systemAudio, segment: 0))
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

    // MARK: - Segments

    /// One kind's unchanging name stem, shared by `fileName(for:segment:)` and
    /// `segmentURLs(for:)` so the two can never disagree about what a kind's files are called.
    private static func stem(for kind: TrackKind) -> String {
        switch kind {
        case .screen: return "screen"
        case .camera: return "camera"
        case .microphone: return "microphone"
        case .systemAudio: return "system-audio"
        }
    }

    private static func fileExtension(for kind: TrackKind) -> String {
        kind.isVideo ? "mov" : "m4a"
    }

    /// The file one on-window ("segment") of a track is written to.
    ///
    /// Window `0` keeps the unsegmented name (`screen.mov`), so a session that never switches
    /// profiles is byte-identical to one recorded before segmenting existed — every existing
    /// session, cache path and test stays valid.
    static func fileName(for kind: TrackKind, segment: Int) -> String {
        let stem = stem(for: kind)
        let ext = fileExtension(for: kind)
        return segment == 0 ? "\(stem).\(ext)" : "\(stem)-\(segment).\(ext)"
    }

    func url(for kind: TrackKind, segment: Int) -> URL {
        rootURL.appendingPathComponent(Self.fileName(for: kind, segment: segment))
    }

    /// Every segment already written for `kind`, ascending by window index.
    ///
    /// A directory listing rather than a sequence of existence probes: a session that switched
    /// a track off and back on twice has windows 0 and 2 but not 1 if window 1 failed to write
    /// anything, and probing "0, 1, 2, …" until one is missing would silently stop at the gap.
    func segmentURLs(for kind: TrackKind) -> [URL] {
        let stem = Self.stem(for: kind)
        let ext = "." + Self.fileExtension(for: kind)
        let names = (try? FileManager.default.contentsOfDirectory(atPath: rootURL.path)) ?? []

        return names
            .compactMap { name -> (index: Int, name: String)? in
                guard name.hasSuffix(ext) else { return nil }
                let base = String(name.dropLast(ext.count))
                if base == stem { return (0, name) }
                guard base.hasPrefix(stem + "-") else { return nil }
                guard let index = Int(base.dropFirst(stem.count + 1)) else { return nil }
                return (index, name)
            }
            .sorted { $0.index < $1.index }
            .map { rootURL.appendingPathComponent($0.name) }
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
