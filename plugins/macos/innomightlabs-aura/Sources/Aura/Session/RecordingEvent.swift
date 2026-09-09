import Foundation

enum RecordingEventKind: String, Codable {
    case recordStart = "record_start"
    case pause
    case resume
    case recordStop = "record_stop"
}

struct RecordingEvent: Encodable {
    let ts: TimeInterval
    let type: RecordingEventKind
    var app: String?

    private enum CodingKeys: String, CodingKey {
        case ts, type, app
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(ts, forKey: .ts)
        try container.encode(type, forKey: .type)
        try container.encodeIfPresent(app, forKey: .app)
    }
}
