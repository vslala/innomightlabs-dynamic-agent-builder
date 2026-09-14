import Foundation

/// What the user asked to record, as distinct from what came back.
///
/// **Behaviour is never derived from this.** The editor decides what it can do from the files
/// that actually exist (`SourceTrackProbe.probeAll`), which is the only honest source: a
/// requested camera track can still come back empty if the device was unplugged mid-recording,
/// and a manifest-driven editor would then offer camera controls for a track with no frames.
/// The manifest is for *explanation* — "Camera was recording but produced no frames" instead of
/// silently promoting the camera-less composition — and for making a session folder
/// self-describing.
struct RecordingManifest: Codable, Equatable, Sendable {
    static let currentSchemaVersion = 1

    var schemaVersion: Int
    var profile: RecordingProfile
    var startedAt: Date
    /// Display names, for labels and diagnostics. Not identifiers: devices come and go, and
    /// nothing is ever resolved from these.
    var screenTargetName: String?
    var cameraName: String?
    var microphoneName: String?

    init(
        schemaVersion: Int = currentSchemaVersion,
        profile: RecordingProfile,
        startedAt: Date,
        screenTargetName: String? = nil,
        cameraName: String? = nil,
        microphoneName: String? = nil
    ) {
        self.schemaVersion = schemaVersion
        self.profile = profile
        self.startedAt = startedAt
        self.screenTargetName = screenTargetName
        self.cameraName = cameraName
        self.microphoneName = microphoneName
    }

    private static func makeEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }

    private static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }

    func write(to url: URL) throws {
        let data = try Self.makeEncoder().encode(self)
        try data.write(to: url, options: .atomic)
    }

    /// `nil` for a missing or malformed file — every pre-Phase-6 session has no
    /// `recording.json`, and that must not be a load failure.
    static func load(from url: URL) -> RecordingManifest? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? Self.makeDecoder().decode(RecordingManifest.self, from: data)
    }
}
