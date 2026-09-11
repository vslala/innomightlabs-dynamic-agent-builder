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
    static let currentSchemaVersion = 2

    /// Roughly how much of the recording each outline block covers, for a short recording.
    static let outlineBlockSeconds: Double = 20
    /// Abridging limit for a block's text.
    static let outlineBlockCharacters = 180
    /// Hard ceiling on outline blocks, so the outline's size is bounded by the cap rather
    /// than by how long the recording happens to be. Blocks widen for a long recording.
    static let maximumOutlineBlocks = 60

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

    /// Deliberately short keys — `i` id, `s` start, `e` end, `t` text — with a legend in the
    /// prompt. Words are the bulk of the payload, so full key names would cost roughly 20
    /// characters each and put a long recording out of reach of the message cap entirely.
    struct Word: Codable, Equatable, Sendable {
        let i: Int
        let s: Double
        let e: Double
        let t: String
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
    /// A coarse map of the **whole** recording, always present: consecutive cues merged into
    /// blocks of roughly `outlineBlockSeconds` with the text abridged.
    ///
    /// Coarse by construction rather than by trimming, because a full phrase-level transcript
    /// of a long recording exceeds the message cap on its own — and an agent that has lost
    /// the shape of the recording cannot even ask a sensible question about it. Precision
    /// comes from `words`; this is for orientation.
    var outline: [Cue]
    var outlineCuesOmitted: Int
    /// The range word detail is provided for. The agent can ask for a different one with
    /// `request_transcript`, rather than being silently given a truncated view.
    var detailFrom: Double?
    var detailTo: Double?
    /// Word-level detail within that range, in recording time.
    var words: [Word]
    var wordsOmitted: Int
    /// Words currently cut. Reversible: the agent can restore any of them by id.
    let excludedWordIds: [Int]

    // MARK: - Building

    /// - Parameter focus: where word detail should be centred when the whole transcript
    ///   won't fit — normally the playhead, since that is what the user is looking at.
    static func make(
        sessionID: String,
        duration: TimeInterval,
        probes: [SourceTrackProbe],
        events: EventTimeline,
        document: SessionEdit,
        transcript: Transcript?,
        /// Seconds to add to a transcript time to get recording time. Passed in rather than
        /// read from the document, because it has to match the offset the composition
        /// actually applies to the microphone lane.
        transcriptOffset: TimeInterval? = nil,
        focus: TimeInterval? = nil,
        detailRange: TimeSpan? = nil
    ) -> SessionDigest {
        let offset = transcriptOffset ?? document.micTimeOffset
        let allWords = (transcript?.allWords ?? []).map {
            Word(i: $0.id, s: round2($0.start + offset), e: round2($0.end + offset), t: $0.text)
        }
        let window = detailRange ?? TimeSpan(start: 0, end: max(duration, 0.01))
        let windowed = allWords.filter { $0.e > window.start && $0.s < window.end }

        return SessionDigest(
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
            // Shifted into recording time: operations are expressed on that clock, and
            // handing over the microphone's own would make every proposed cut land wrong.
            outline: outlineBlocks(
                segments: transcript?.segments ?? [],
                offset: offset,
                totalDuration: duration
            ),
            outlineCuesOmitted: 0,
            detailFrom: windowed.isEmpty ? nil : round2(window.start),
            detailTo: windowed.isEmpty ? nil : round2(window.end),
            words: windowed,
            wordsOmitted: allWords.count - windowed.count,
            excludedWordIds: document.excludedWords.map(\.id).sorted()
        )
    }

    /// Merges consecutive cues into bounded blocks.
    static func outlineBlocks(
        segments: [Transcript.Segment],
        offset: TimeInterval,
        totalDuration: TimeInterval
    ) -> [Cue] {
        // Widen the blocks for a long recording so the block count — and therefore the
        // outline's size — stays bounded either way. Measured against the transcript's own
        // extent as well as the declared duration, so a transcript that overruns the media
        // can't slip past the cap.
        let extent = max(totalDuration, segments.last?.end ?? 0)
        let blockSeconds = max(outlineBlockSeconds, extent / Double(maximumOutlineBlocks))
        var blocks: [Cue] = []
        var start: TimeInterval?
        var end: TimeInterval = 0
        var pieces: [String] = []

        func flush() {
            guard let blockStart = start, !pieces.isEmpty else { return }
            var text = pieces.joined(separator: " ")
            if text.count > outlineBlockCharacters {
                text = String(text.prefix(outlineBlockCharacters)) + "…"
            }
            blocks.append(Cue(start: round2(blockStart + offset), end: round2(end + offset), text: text))
            start = nil
            pieces = []
        }

        for segment in segments {
            if start == nil { start = segment.start }
            end = segment.end
            pieces.append(segment.text)
            if end - (start ?? end) >= blockSeconds { flush() }
        }
        flush()

        return blocks
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

    /// The share of the budget the outline may occupy before it starts being trimmed.
    /// Reserving the rest for word detail is what stops a long recording's outline from
    /// squeezing out the precision the agent actually edits with.
    static let outlineBudgetShare = 0.45

    /// The digest, shrunk until its JSON fits the budget.
    ///
    /// Both halves are guaranteed a share rather than one being sacrificed to the other. The
    /// outline keeps the agent oriented and lets it ask for what it needs via
    /// `request_transcript`; the word detail is what it edits with. Whatever is dropped is
    /// counted, so the agent knows it is looking at a partial view rather than assuming the
    /// recording ends where the data does.
    func fitting(characterBudget: Int) -> SessionDigest {
        guard compactJSON().count > characterBudget else { return self }

        // Bound the outline to its share first, measured without any word detail.
        var trimmed = self
        let outlineShare = Int(Double(characterBudget) * Self.outlineBudgetShare)
        if keepingWords(0).compactJSON().count > outlineShare {
            trimmed = Self.largestFit(upTo: outline.count, budget: outlineShare, build: {
                keepingWords(0).keepingOutline($0)
            }) ?? keepingWords(0).keepingOutline(0)
            trimmed.words = words
            trimmed.wordsOmitted = wordsOmitted
        }

        // Then fill the remainder with as much word detail as fits, keeping the centre of
        // the window.
        return Self.largestFit(upTo: trimmed.words.count, budget: characterBudget, build: {
            trimmed.keepingWords($0)
        }) ?? trimmed.keepingWords(0)
    }

    /// Binary search for the largest `count` whose built digest still fits.
    private static func largestFit(
        upTo limit: Int,
        budget: Int,
        build: (Int) -> SessionDigest
    ) -> SessionDigest? {
        var low = 0
        var high = limit
        var best: SessionDigest?

        while low <= high {
            let mid = (low + high) / 2
            let candidate = build(mid)
            if candidate.compactJSON().count <= budget {
                best = candidate
                low = mid + 1
            } else {
                high = mid - 1
            }
        }
        return best
    }

    /// Keeps `count` words centred on the detail window, so trimming narrows around the point
    /// of interest rather than lopping off the end.
    private func keepingWords(_ count: Int) -> SessionDigest {
        let kept = min(max(0, count), words.count)
        var copy = self

        if kept == 0 {
            copy.words = []
            copy.detailFrom = nil
            copy.detailTo = nil
        } else {
            let start = max(0, (words.count - kept) / 2)
            let slice = Array(words[start..<(start + kept)])
            copy.words = slice
            copy.detailFrom = slice.first?.s
            copy.detailTo = slice.last?.e
        }
        copy.wordsOmitted = wordsOmitted + (words.count - kept)
        return copy
    }

    private func keepingOutline(_ count: Int) -> SessionDigest {
        let kept = min(max(0, count), outline.count)
        var copy = self
        copy.outline = Array(outline.prefix(kept))
        copy.outlineCuesOmitted = outlineCuesOmitted + (outline.count - kept)
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
