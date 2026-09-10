import Foundation

/// Places `events.jsonl` entries on the pause-compacted timeline the media files use.
///
/// `RecordingEvent.ts` is wall-clock seconds since record start, but `PauseClock` strips
/// paused time out of the media files, so after any pause the two clocks diverge by the
/// total paused duration. Events written since `media_ts` exists carry the answer; older
/// logs are converted here using their own pause/resume entries, which is enough to
/// recover it exactly.
struct EventTimeline: Equatable {
    struct Entry: Equatable {
        let event: RecordingEvent
        let mediaTs: TimeInterval
    }

    let entries: [Entry]

    var markers: [Entry] { entries.filter { $0.event.type == .userMarker } }
    var screenshots: [Entry] { entries.filter { $0.event.type == .screenSnapshot } }
    var failedTracks: [Entry] { entries.filter { $0.event.type == .trackFailed } }

    /// Pure. Events are assumed to be in the order they were logged, which is the order
    /// an append-only `EventLogWriter` produces.
    init(events: [RecordingEvent]) {
        var accumulatedPausedDuration: TimeInterval = 0
        var pauseStartedAt: TimeInterval?

        entries = events.map { event in
            switch event.type {
            case .pause:
                if pauseStartedAt == nil {
                    pauseStartedAt = event.ts
                }
            case .resume:
                if let start = pauseStartedAt {
                    accumulatedPausedDuration += event.ts - start
                    pauseStartedAt = nil
                }
            default:
                break
            }

            // An event logged while paused belongs at the instant the pause began — that
            // is the only media time it can map to, since the paused span is not in the files.
            let wallTs = pauseStartedAt ?? event.ts
            let recovered = max(0, wallTs - accumulatedPausedDuration)
            return Entry(event: event, mediaTs: event.mediaTs ?? recovered)
        }
    }

    /// Reads and converts a session's event log. Malformed lines are skipped rather than
    /// failing the load — a truncated final line is expected if the app died mid-write.
    static func load(eventsURL: URL) -> EventTimeline {
        guard let contents = try? String(contentsOf: eventsURL, encoding: .utf8) else {
            return EventTimeline(events: [])
        }

        let decoder = JSONDecoder()
        let events = contents
            .split(separator: "\n", omittingEmptySubsequences: true)
            .compactMap { line -> RecordingEvent? in
                guard let data = line.data(using: .utf8) else { return nil }
                return try? decoder.decode(RecordingEvent.self, from: data)
            }
        return EventTimeline(events: events)
    }
}
