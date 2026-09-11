import Foundation

/// A compact, complete description of one recording, written to `digest.json` and sent to the
/// agent verbatim.
///
/// Rich because the agent can only propose sound edits if it knows what actually happened —
/// which tracks exist and how long they are, where the recording was paused, what the user
/// flagged, what has already been edited, and what was said. Compact because the A2A message
/// cap is 32,000 characters and the instruction has to fit alongside it: keys are short,
/// times are rounded to centiseconds, and the transcript is the first thing trimmed.
///
/// Sent as JSON rather than prose on purpose. It is unambiguous for the agent, and because the
/// same bytes are persisted, a suggestion that looks wrong can be diagnosed by reading exactly
/// what the agent was told.
struct SessionDigest: Codable, Equatable, Sendable {
    static let currentSchemaVersion = 1

    struct Track: Codable, Equatable, Sendable {
        let kind: String
        let seconds: Double
        var size: String?
        /// Startup delay recorded at capture time, and the correction applied to realign it.
        var startOffset: Double?
        var syncCorrection: Double?
    }

    struct Span: Codable, Equatable, Sendable {
        let start: Double
        let end: Double
    }

    struct Mark: Codable, Equatable, Sendable {
        let at: Double
        let label: String
    }

    struct Overlay: Codable, Equatable, Sendable {
        let at: Double
        let visible: Bool
        /// `[x, y, width, height]`, normalized. An array rather than an object purely to save
        /// characters against the message cap.
        let rect: [Double]
    }

    struct Lane: Codable, Equatable, Sendable {
        let lane: String
        let muted: Bool
        let slipMs: Int
    }

    struct Cue: Codable, Equatable, Sendable {
        let start: Double
        let end: Double
        let text: String
    }

    let schemaVersion: Int
    let sessionId: String
    let durationSeconds: Double
    let tracks: [Track]
    let pauses: [Span]
    let markers: [Mark]
    let screenshots: [Double]
    let trackFailures: [String]
    /// The current edit: which spans of the recording survive, in order.
    let keptSpans: [Span]
    let cameraOverlay: [Overlay]
    let audioLanes: [Lane]
    /// In recording time, already shifted out of the microphone file's own clock.
    let transcript: [Cue]
    var transcriptCuesOmitted: Int

    // MARK: - Building

    static func make(
        sessionID: String,
        duration: TimeInterval,
        probes: [SourceTrackProbe],
        events: EventTimeline,
        document: SessionEdit,
        transcript: Transcript?
    ) -> SessionDigest {
        SessionDigest(
            schemaVersion: currentSchemaVersion,
            sessionId: sessionID,
            durationSeconds: round2(duration),
            tracks: probes.map { probe in
                Track(
                    kind: probe.kind.rawValue,
                    seconds: round2(Timeline.seconds(probe.duration)),
                    size: probe.displaySize.map { "\(Int($0.width))x\(Int($0.height))" },
                    startOffset: nonZero(Timeline.seconds(probe.recordedStartOffset)),
                    syncCorrection: nonZero(Timeline.seconds(probe.alignmentCorrection))
                )
            },
            pauses: pauseSpans(in: events),
            markers: events.markers.map { Mark(at: round2($0.mediaTs), label: $0.event.label ?? "marker") },
            screenshots: events.screenshots.map { round2($0.mediaTs) },
            trackFailures: events.failedTracks.compactMap { $0.event.label },
            keptSpans: document.clips.map { Span(start: round2($0.source.start), end: round2($0.source.end)) },
            cameraOverlay: document.cameraOverlay.sorted { $0.t < $1.t }.map { keyframe in
                Overlay(
                    at: round2(keyframe.t),
                    visible: keyframe.visible,
                    rect: [keyframe.rect.x, keyframe.rect.y, keyframe.rect.width, keyframe.rect.height]
                        .map { round2($0) }
                )
            },
            audioLanes: document.audioLanes.map {
                Lane(lane: $0.lane.rawValue, muted: $0.muted, slipMs: Int(($0.offset * 1000).rounded()))
            },
            transcript: (transcript?.segments ?? []).map { segment in
                // Shifted into recording time: operations are expressed on that clock, and
                // handing over the microphone's own would make every proposed cut land wrong.
                Cue(
                    start: round2(segment.start + document.micTimeOffset),
                    end: round2(segment.end + document.micTimeOffset),
                    text: segment.text
                )
            },
            transcriptCuesOmitted: 0
        )
    }

    /// Pause/resume pairs, on the media timeline. Useful context: a pause is usually where the
    /// user stopped to think, which is often exactly where an edit belongs.
    private static func pauseSpans(in events: EventTimeline) -> [Span] {
        var spans: [Span] = []
        var pausedAt: TimeInterval?

        for entry in events.entries {
            switch entry.event.type {
            case .pause where pausedAt == nil:
                pausedAt = entry.mediaTs
            case .resume:
                if let start = pausedAt {
                    spans.append(Span(start: round2(start), end: round2(entry.mediaTs)))
                    pausedAt = nil
                }
            default:
                break
            }
        }
        return spans
    }

    // MARK: - Serialising

    /// Compact JSON — no pretty printing, no escaped slashes — for sending to the agent.
    func compactJSON() -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.withoutEscapingSlashes]
        guard let data = try? encoder.encode(self) else { return "{}" }
        return String(decoding: data, as: UTF8.self)
    }

    /// Pretty JSON for `digest.json`, which is meant to be read by a person.
    func write(to url: URL) {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        guard let data = try? encoder.encode(self) else { return }
        try? data.write(to: url, options: .atomic)
    }

    /// The digest, shrunk until its JSON fits the budget.
    ///
    /// Only the transcript is trimmed, and from the end: everything else is small, bounded,
    /// and structural, whereas a long recording's transcript is unbounded. Dropping cues is
    /// reported in `transcriptCuesOmitted` so the agent knows it is not seeing everything
    /// rather than silently assuming the recording ends early.
    func fitting(characterBudget: Int) -> SessionDigest {
        guard compactJSON().count > characterBudget else { return self }

        var low = 0
        var high = transcript.count
        var best = truncatingTranscript(to: 0)

        // Binary search for the most cues that still fit.
        while low <= high {
            let mid = (low + high) / 2
            let candidate = truncatingTranscript(to: mid)
            if candidate.compactJSON().count <= characterBudget {
                best = candidate
                low = mid + 1
            } else {
                high = mid - 1
            }
        }
        return best
    }

    private func truncatingTranscript(to count: Int) -> SessionDigest {
        var copy = self
        let kept = min(max(0, count), transcript.count)
        copy = SessionDigest(
            schemaVersion: schemaVersion,
            sessionId: sessionId,
            durationSeconds: durationSeconds,
            tracks: tracks,
            pauses: pauses,
            markers: markers,
            screenshots: screenshots,
            trackFailures: trackFailures,
            keptSpans: keptSpans,
            cameraOverlay: cameraOverlay,
            audioLanes: audioLanes,
            transcript: Array(transcript.prefix(kept)),
            transcriptCuesOmitted: transcript.count - kept
        )
        return copy
    }

    private static func round2(_ value: Double) -> Double {
        guard value.isFinite else { return 0 }
        return (value * 100).rounded() / 100
    }

    private static func nonZero(_ value: Double) -> Double? {
        let rounded = round2(value)
        return rounded == 0 ? nil : rounded
    }
}
