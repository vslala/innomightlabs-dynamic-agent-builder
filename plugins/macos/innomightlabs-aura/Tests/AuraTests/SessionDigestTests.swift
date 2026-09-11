import XCTest
import AVFoundation
@testable import Aura

final class SessionDigestTests: XCTestCase {
    private func probe(_ kind: TrackKind, seconds: TimeInterval = 54.23, recordedOffset: TimeInterval = 0) -> SourceTrackProbe {
        SourceTrackProbe(
            url: URL(fileURLWithPath: "/tmp/\(kind.rawValue)"),
            kind: kind,
            duration: Timeline.time(seconds: seconds),
            displaySize: kind.isVideo ? CGSize(width: 2560, height: 1440) : nil,
            preferredTransform: .identity,
            recordedStartOffset: Timeline.time(seconds: recordedOffset)
        )
    }

    private func transcript(_ count: Int) -> Transcript {
        Transcript(
            source: "microphone.m4a",
            engine: "test",
            language: "en",
            segments: (0..<count).map {
                Transcript.Segment(id: $0, start: Double($0), end: Double($0) + 0.9, text: "cue number \($0) said something", words: nil)
            }
        )
    }

    private func digest(
        document: SessionEdit = .initial(duration: 54.23),
        events: EventTimeline = EventTimeline(events: []),
        transcript: Transcript? = nil,
        probes: [SourceTrackProbe]? = nil
    ) -> SessionDigest {
        SessionDigest.make(
            sessionID: "20260909-215437-6d81",
            duration: 54.23,
            probes: probes ?? [probe(.screen), probe(.camera), probe(.microphone, recordedOffset: 0.4)],
            events: events,
            document: document,
            transcript: transcript
        )
    }

    // MARK: - Richness: everything the agent needs

    func testDigestDescribesTheTracksIncludingSyncCorrection() {
        let subject = digest()

        XCTAssertEqual(subject.tracks.map(\.kind), ["screen", "camera", "microphone"])
        XCTAssertEqual(subject.tracks.first?.size, "2560x1440")
        let mic = subject.tracks.first { $0.kind == "microphone" }
        XCTAssertEqual(mic?.startOffset ?? 0, 0.4, accuracy: 0.001)
        XCTAssertEqual(mic?.syncCorrection ?? 0, 0.4, accuracy: 0.001)
    }

    func testZeroOffsetsAreOmittedRatherThanSentAsNoise() {
        // Every byte competes with the transcript for the message budget.
        let subject = digest(probes: [probe(.screen)])

        XCTAssertNil(subject.tracks.first?.startOffset)
        XCTAssertNil(subject.tracks.first?.syncCorrection)
    }

    func testDigestIncludesPausesMarkersScreenshotsAndFailures() {
        let events = EventTimeline(events: [
            RecordingEvent(ts: 0, type: .recordStart, mediaTs: 0),
            RecordingEvent(ts: 10, type: .pause, mediaTs: 10),
            RecordingEvent(ts: 14, type: .resume, mediaTs: 10),
            RecordingEvent(ts: 20, type: .userMarker, mediaTs: 16, label: "mistake"),
            RecordingEvent(ts: 25, type: .screenSnapshot, mediaTs: 21, path: "screenshots/25.0.png"),
            RecordingEvent(ts: 30, type: .trackFailed, mediaTs: 26, label: "camera.mov died")
        ])

        let subject = digest(events: events)

        XCTAssertEqual(subject.pauses, [SessionDigest.Span(start: 10, end: 10)])
        XCTAssertEqual(subject.markers.map(\.label), ["mistake"])
        XCTAssertEqual(subject.markers.first?.at, 16)
        XCTAssertEqual(subject.screenshots, [21])
        XCTAssertEqual(subject.trackFailures, ["camera.mov died"])
    }

    func testDigestDescribesTheCurrentEditNotJustTheRecording() throws {
        let document = try SessionEdit.initial(duration: 54.23)
            .applying(.removeRange(TimeSpan(start: 10, end: 20)))
            .applying(.setLaneMuted(lane: .systemAudio, muted: true))
            .applying(.setLaneOffset(lane: .microphone, seconds: -0.05))

        let subject = digest(document: document)

        XCTAssertEqual(subject.keptSpans, [
            SessionDigest.Span(start: 0, end: 10),
            SessionDigest.Span(start: 20, end: 54.23)
        ])
        XCTAssertEqual(subject.audioLanes.first { $0.lane == "system_audio" }?.muted, true)
        XCTAssertEqual(subject.audioLanes.first { $0.lane == "microphone" }?.slipMs, -50)
    }

    func testCameraOverlayIsSentAsAFourElementRect() {
        // An array rather than an object, purely to save characters against the message cap.
        let subject = digest()

        XCTAssertEqual(subject.cameraOverlay.count, 1)
        XCTAssertEqual(subject.cameraOverlay.first?.rect.count, 4)
        XCTAssertEqual(subject.cameraOverlay.first?.visible, true)
    }

    func testTranscriptIsShiftedIntoRecordingTime() {
        // The digest's clock must be the clock operations use, or every AI cut lands wrong.
        let document = SessionEdit.initial(duration: 54.23, micTimeOffset: 0.4)
        let subject = digest(document: document, transcript: transcript(3))

        XCTAssertEqual(subject.transcript.first?.start ?? 0, 0.4, accuracy: 0.001)
        XCTAssertEqual(subject.transcript.first?.end ?? 0, 1.3, accuracy: 0.001)
    }

    // MARK: - Compactness: fitting the message cap

    func testDigestIsCompactJSONWithoutPrettyPrinting() {
        let json = digest(transcript: transcript(5)).compactJSON()

        XCTAssertFalse(json.contains("\n"))
        XCTAssertTrue(json.hasPrefix("{"))
    }

    func testTimesAreRoundedToCentiseconds() {
        let document = SessionEdit.initial(duration: 1.0 / 3.0)
        let json = digest(document: document).compactJSON()

        // 0.3333333… would otherwise cost 17 characters per number.
        XCTAssertFalse(json.contains("0.3333"))
    }

    func testOversizedDigestIsTrimmedToFitTheBudget() {
        let big = digest(transcript: transcript(4_000))
        XCTAssertGreaterThan(big.compactJSON().count, 20_000)

        let fitted = big.fitting(characterBudget: 20_000)

        XCTAssertLessThanOrEqual(fitted.compactJSON().count, 20_000)
        XCTAssertGreaterThan(fitted.transcript.count, 0, "should keep as much transcript as fits")
        XCTAssertLessThan(fitted.transcript.count, 4_000)
    }

    func testTrimmingReportsWhatWasDropped() {
        // So the agent knows it is not seeing the whole recording, rather than assuming the
        // transcript simply ends there.
        let fitted = digest(transcript: transcript(4_000)).fitting(characterBudget: 8_000)

        XCTAssertGreaterThan(fitted.transcriptCuesOmitted, 0)
        XCTAssertEqual(fitted.transcriptCuesOmitted, 4_000 - fitted.transcript.count)
    }

    func testTrimmingKeepsTheStructuralFactsAndOnlyDropsTranscript() {
        let events = EventTimeline(events: [
            RecordingEvent(ts: 20, type: .userMarker, mediaTs: 20, label: "important")
        ])
        let fitted = digest(events: events, transcript: transcript(4_000))
            .fitting(characterBudget: 3_000)

        XCTAssertEqual(fitted.markers.map(\.label), ["important"])
        XCTAssertEqual(fitted.tracks.count, 3)
        XCTAssertFalse(fitted.keptSpans.isEmpty)
    }

    func testAlreadySmallDigestIsUntouched() {
        let small = digest(transcript: transcript(5))

        XCTAssertEqual(small.fitting(characterBudget: 32_000), small)
    }

    func testDigestRoundTripsThroughJSON() throws {
        let subject = digest(transcript: transcript(10))
        let data = try JSONEncoder().encode(subject)

        XCTAssertEqual(try JSONDecoder().decode(SessionDigest.self, from: data), subject)
    }

    func testDigestPersistsToDisk() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-digest-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let url = directory.appendingPathComponent("digest.json")
        digest(transcript: transcript(3)).write(to: url)

        let reloaded = try JSONDecoder().decode(SessionDigest.self, from: try Data(contentsOf: url))
        XCTAssertEqual(reloaded.sessionId, "20260909-215437-6d81")
        XCTAssertEqual(reloaded.transcript.count, 3)
    }

    // MARK: - The prompt built around it

    func testPromptEmbedsTheDigestAndStaysWithinTheMessageCap() {
        let context = EditSuggestionContext(
            sessionID: "20260909-215437-6d81",
            duration: 54.23,
            transcript: transcript(4_000),
            document: .initial(duration: 54.23),
            markers: [],
            digest: digest(transcript: transcript(4_000))
        )

        let prompt = EditSuggestionPrompt.build(
            instruction: "cut the boring bits",
            context: context,
            characterBudget: InnomightLabsEditSuggester.maximumMessageCharacters
        )

        XCTAssertLessThanOrEqual(prompt.count, InnomightLabsEditSuggester.maximumMessageCharacters)
        XCTAssertTrue(prompt.contains("SESSION DIGEST (JSON):"))
        XCTAssertTrue(prompt.contains("cut the boring bits"))
        XCTAssertTrue(prompt.contains("\"sessionId\":\"20260909-215437-6d81\""))
    }

    func testPromptStillDeclaresEveryOperation() {
        let prompt = EditSuggestionPrompt.build(
            instruction: "tidy up",
            context: EditSuggestionContext(
                sessionID: "s", duration: 10, transcript: nil,
                document: .initial(duration: 10), markers: [], digest: nil
            ),
            characterBudget: 32_000
        )

        for op in ["remove_range", "split_clip", "set_overlay_keyframe", "remove_overlay_keyframe",
                   "set_lane_gain", "set_lane_muted", "set_lane_offset"] {
            XCTAssertTrue(prompt.contains(op), "the agent isn't told about \(op)")
        }
    }

    func testPromptWorksWithoutAPrebuiltDigest() {
        let prompt = EditSuggestionPrompt.build(
            instruction: "help",
            context: EditSuggestionContext(
                sessionID: "s1", duration: 10, transcript: nil,
                document: .initial(duration: 10), markers: [], digest: nil
            ),
            characterBudget: 32_000
        )

        XCTAssertTrue(prompt.contains("\"sessionId\":\"s1\""))
    }

    func testConversationKeyIsStableAndSessionScoped() {
        // One durable conversation per recording, derived rather than persisted.
        let a = EditSuggestionContext(sessionID: "sess-a", duration: 1, transcript: nil,
                                      document: .initial(duration: 1), markers: [], digest: nil)
        let b = EditSuggestionContext(sessionID: "sess-b", duration: 1, transcript: nil,
                                      document: .initial(duration: 1), markers: [], digest: nil)

        XCTAssertEqual(a.conversationKey, "aura-session-sess-a")
        XCTAssertNotEqual(a.conversationKey, b.conversationKey)
    }
}
