import CoreMedia
import Foundation

/// Reads an `edit.json` of any schema version.
///
/// Migration lives here rather than in `SessionEdit.init(from:)` on purpose. The v2 decoder is
/// strict about `cuts` and `recordingDuration` precisely so that a malformed v2 document fails
/// loudly instead of decoding as "nothing was cut" and discarding every edit. A tolerant
/// decoder that understood both shapes would give that guarantee up. So the version is
/// inspected first, and a v1 payload is decoded through its own mirror type and converted.
enum SessionEditMigration {
    /// v1: a mutable clip list plus a separate word-exclusion list.
    private struct V1: Decodable {
        struct Clip: Decodable {
            let source: TimeSpan
        }

        let schemaVersion: Int
        let micTimeOffset: TimeInterval?
        let clips: [Clip]
        let excludedWords: [ExcludedWord]?
        let cameraOverlay: [OverlayKeyframe]
        let audioLanes: [AudioLaneSettings]
        let cameraStyle: PiPStyle?
    }

    private struct VersionProbe: Decodable {
        let schemaVersion: Int
    }

    enum Outcome: Equatable {
        case current(SessionEdit)
        /// Converted from an older schema. The caller should back up the original before
        /// overwriting it.
        case migrated(SessionEdit)
        case unreadable
        /// Written by a newer build than this one; refuse rather than half-read it.
        case tooNew
    }

    /// - Parameter recordingDuration: the recording's extent, needed because v1 did not store
    ///   it. Must come from the probed media, not from `clips.last.source.end` — if the user
    ///   ever cut the tail, the last clip ends early and using it would silently and
    ///   irreversibly truncate the timeline, in a way indistinguishable from the recording
    ///   having ended there.
    static func decode(_ data: Data, recordingDuration: TimeInterval) -> Outcome {
        guard let version = try? JSONDecoder().decode(VersionProbe.self, from: data).schemaVersion else {
            return .unreadable
        }

        if version > SessionEdit.currentSchemaVersion { return .tooNew }

        if version == SessionEdit.currentSchemaVersion {
            guard let document = try? JSONDecoder().decode(SessionEdit.self, from: data) else {
                return .unreadable
            }
            return .current(document)
        }

        guard let v1 = try? JSONDecoder().decode(V1.self, from: data) else { return .unreadable }
        guard let migrated = migrate(v1, recordingDuration: recordingDuration) else { return .unreadable }
        return .migrated(migrated)
    }

    /// Turns a v1 clip list back into the removals that produced it.
    ///
    /// Returns nil when the clips are not ascending and disjoint, rather than guessing: a
    /// wrong inversion would move every subsequent edit.
    private static func migrate(_ v1: V1, recordingDuration: TimeInterval) -> SessionEdit? {
        let clips = v1.clips.map(\.source).sorted { $0.start < $1.start }
        for (earlier, later) in zip(clips, clips.dropFirst()) where later.start < earlier.end {
            return nil
        }

        let limit = max(recordingDuration, clips.last?.end ?? 0)
        var cuts: [Cut] = []
        var splitPoints: [TimeInterval] = []
        var cursor: TimeInterval = 0

        for clip in clips where !clip.isEmpty {
            if clip.start > cursor {
                // A gap between surviving clips is a range cut.
                cuts.append(Cut(span: TimeSpan(start: cursor, end: clip.start), origin: .range))
            } else if clip.start == cursor, cursor > 0 {
                // Touching clips came from a split, which removed nothing. Looking only for
                // gaps would make every split the user ever made silently vanish.
                splitPoints.append(cursor)
            }
            cursor = max(cursor, clip.end)
        }

        // The trailing cut is the one that gets forgotten. Omitting it lengthens the timeline
        // and shifts every resume position.
        if cursor < limit {
            cuts.append(Cut(span: TimeSpan(start: cursor, end: limit), origin: .range))
        }

        // v1 `ExcludedWord` spans are already in session time — the repair pass put them
        // there — so `micTimeOffset` must NOT be applied again. With `micTimeOffset: 0` on a
        // real document a double application would not show up in testing.
        for word in v1.excludedWords ?? [] where word.end > word.start {
            cuts.append(Cut(
                span: TimeSpan(start: word.start, end: word.end),
                origin: .word(id: word.id, text: word.text)
            ))
        }

        return SessionEdit(
            recordingDuration: limit,
            cuts: cuts,
            splitPoints: splitPoints,
            markers: [],
            micTimeOffset: v1.micTimeOffset ?? 0,
            cameraOverlay: v1.cameraOverlay,
            audioLanes: v1.audioLanes,
            cameraStyle: v1.cameraStyle ?? .plain,
            // Unknown: the v1 document never recorded which transcript its word ids came from,
            // so the first reconcile against a known transcript adopts it.
            transcriptIdentity: nil
        )
    }
}
