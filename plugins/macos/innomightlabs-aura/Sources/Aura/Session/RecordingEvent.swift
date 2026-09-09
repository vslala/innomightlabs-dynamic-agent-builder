import Foundation

enum RecordingEventKind: String, Codable {
    case recordStart = "record_start"
    case pause
    case resume
    case recordStop = "record_stop"
    case userMarker = "user_marker"
    case screenSnapshot = "screen_snapshot"
}

struct RecordingEvent: Encodable {
    let ts: TimeInterval
    let type: RecordingEventKind
    var app: String? = nil
    var label: String? = nil
    var path: String? = nil

    private enum CodingKeys: String, CodingKey {
        case ts, type, app, label, path
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(ts, forKey: .ts)
        try container.encode(type, forKey: .type)
        try container.encodeIfPresent(app, forKey: .app)
        try container.encodeIfPresent(label, forKey: .label)
        try container.encodeIfPresent(path, forKey: .path)
    }
}
