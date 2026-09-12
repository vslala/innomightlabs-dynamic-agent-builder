import XCTest
@testable import Aura

final class WordLevelEditingTests: XCTestCase {
    private func word(_ id: Int, _ start: TimeInterval, _ end: TimeInterval, _ text: String) -> Transcript.Word {
        Transcript.Word(id: id, start: start, end: end, text: text)
    }

    private func excluded(_ word: Transcript.Word) -> ExcludedWord {
        ExcludedWord(id: word.id, start: word.start, end: word.end, text: word.text)
    }

    private func transcript(_ words: [Transcript.Word]) -> Transcript {
        Transcript(
            source: "microphone.m4a", engine: "test", language: "en",
            segments: [Transcript.Segment(
                id: 0,
                start: words.first?.start ?? 0,
                end: words.last?.end ?? 0,
                text: words.map(\.text).joined(separator: " "),
                words: words
            )]
        )
    }

    // MARK: - Cleaning what the model actually produced
    //
    // Every cue in a real recording arrived polluted with Whisper control markup, which the
    // agent was reading as if it were speech.

    func testSpecialTokensAreStripped() {
        let raw = "<|startoftranscript|><|en|><|transcribe|><|0.00|> Hey everyone, so today.<|10.88|>"

        XCTAssertEqual(Transcript.cleaned(raw), "Hey everyone, so today.")
    }

    func testCleaningCollapsesTheWhitespaceItLeaves() {
        XCTAssertEqual(Transcript.cleaned("<|0.00|>  a   b  <|1.0|>"), "a b")
    }

    func testCueTextIsRebuiltFromItsWordsWhichAreAlreadyClean() {
        let segments = [Transcript.Segment(
            id: 0, start: 1, end: 2,
            text: "<|startoftranscript|> polluted <|1.0|>",
            words: [word(0, 1.0, 1.4, "Hey"), word(0, 1.5, 2.0, "everyone,")]
        )]

        let normalized = Transcript.normalized(segments: segments, mediaDuration: 10)

        XCTAssertEqual(normalized.first?.text, "Hey everyone,")
    }

    func testHallucinatedSpeechPastTheEndOfTheRecordingIsDropped() {
        // A real 265s recording produced "[BLANK_AUDIO]" at 291.8s.
        let segments = [
            Transcript.Segment(id: 0, start: 1, end: 2, text: "real", words: [word(0, 1, 2, "real")]),
            Transcript.Segment(id: 0, start: 289, end: 291.8, text: "[BLANK_AUDIO]", words: [word(0, 289, 291.8, "[BLANK_AUDIO]")])
        ]

        let normalized = Transcript.normalized(segments: segments, mediaDuration: 265.28)

        XCTAssertEqual(normalized.count, 1)
        XCTAssertEqual(normalized.first?.text, "real")
    }

    func testWordsAreClampedToTheRecordingLength() {
        let segments = [Transcript.Segment(
            id: 0, start: 264, end: 267, text: "trailing",
            words: [word(0, 264, 267, "trailing")]
        )]

        let normalized = Transcript.normalized(segments: segments, mediaDuration: 265.28)

        XCTAssertEqual(normalized.first?.words.first?.end ?? 0, 265.28, accuracy: 0.001)
    }

    func testWordIDsAreDenseAndUniqueAcrossTheTranscript() {
        var segments: [Transcript.Segment] = []
        for index in 0..<3 {
            let base = Double(index)
            let first: Transcript.Word = word(0, base, base + 0.4, "a")
            let second: Transcript.Word = word(0, base + 0.5, base + 0.9, "b")
            segments.append(Transcript.Segment(
                id: 0,
                start: base,
                end: base + 1,
                text: "x",
                words: [first, second]
            ))
        }

        let normalized = Transcript.normalized(segments: segments, mediaDuration: 10)
        let ids: [Int] = normalized.flatMap { segment in segment.words.map { $0.id } }

        XCTAssertEqual(ids, Array(0..<6))
    }

    func testEmptyCuesAreDropped() {
        let segments = [Transcript.Segment(id: 0, start: 1, end: 2, text: "<|1.0|>", words: [])]

        XCTAssertTrue(Transcript.normalized(segments: segments, mediaDuration: 10).isEmpty)
    }

    func testV1TranscriptsAreRejectedSoTheyGetRegenerated() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-t-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let url = directory.appendingPathComponent("transcript.json")
        var old = transcript([word(0, 1, 2, "hi")])
        old.schemaVersion = 1
        try JSONEncoder().encode(old).write(to: url)

        XCTAssertNil(Transcript.load(from: url), "a polluted v1 transcript must be re-run, not patched")
    }

    // MARK: - Reversible word exclusion

    func testExcludingAWordShortensTheTimelineByExactlyThatWord() throws {
        let target = word(3, 10.0, 10.4, "um")
        let edit = try SessionEdit.initial(duration: 60).applying(.excludeWords([excluded(target)]))

        XCTAssertEqual(edit.duration, 60 - 0.4, accuracy: 0.001)
        XCTAssertTrue(edit.isExcluded(wordID: 3))
    }

    func testRestoringAWordPutsTheTimelineBack() throws {
        let target = word(3, 10.0, 10.4, "um")
        let edit = try SessionEdit.initial(duration: 60)
            .applying(.excludeWords([excluded(target)]))
            .applying(.restoreWords(ids: [3]))

        XCTAssertEqual(edit.duration, 60, accuracy: 0.001)
        XCTAssertFalse(edit.isExcluded(wordID: 3))
    }

    func testWordsCanBeRestoredIndividuallyAndOutOfOrder() throws {
        // The point of keeping them rather than deleting them: undoing one word months later
        // shouldn't mean unwinding everything done since.
        let words = [word(0, 1, 1.2, "um"), word(1, 5, 5.3, "uh"), word(2, 9, 9.2, "so")]
        var edit = try SessionEdit.initial(duration: 60).applying(.excludeWords(words.map(excluded)))
        XCTAssertEqual(edit.excludedWords.count, 3)

        edit = try edit.applying(.restoreWords(ids: [1]))

        XCTAssertEqual(edit.excludedWords.map(\.id), [0, 2])
        XCTAssertTrue(edit.isExcluded(wordID: 0))
        XCTAssertFalse(edit.isExcluded(wordID: 1))
    }

    func testExcludingTheSameWordTwiceIsIdempotent() throws {
        let target = word(3, 10.0, 10.4, "um")
        let edit = try SessionEdit.initial(duration: 60)
            .applying(.excludeWords([excluded(target)]))
            .applying(.excludeWords([excluded(target)]))

        XCTAssertEqual(edit.excludedWords.count, 1)
    }

    func testExclusionsAndCoarseCutsCompose() throws {
        // Two independent layers: a range cut and a word cut must both apply.
        let edit = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 20, end: 30)))
            .applying(.excludeWords([excluded(word(0, 5, 5.5, "um"))]))

        XCTAssertEqual(edit.duration, 60 - 10 - 0.5, accuracy: 0.001)
    }

    func testAWordInsideAnAlreadyCutRangeRemovesNothingExtra() throws {
        let edit = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 20, end: 30)))
            .applying(.excludeWords([excluded(word(0, 25, 25.4, "um"))]))

        XCTAssertEqual(edit.duration, 50, accuracy: 0.001)
        XCTAssertTrue(edit.isExcluded(wordID: 0), "still recorded, so it can be restored")
    }

    func testCuttingEveryWordIsRejected() {
        let everything = ExcludedWord(id: 0, start: 0, end: 60, text: "all of it")

        XCTAssertThrowsError(try SessionEdit.initial(duration: 60).applying(.excludeWords([everything]))) { error in
            XCTAssertEqual(error as? EditOperationError, .wouldRemoveEntireTimeline)
        }
    }

    func testEmptyWordListIsRejected() {
        XCTAssertThrowsError(try SessionEdit.initial(duration: 60).applying(.excludeWords([]))) { error in
            XCTAssertEqual(error as? EditOperationError, .noWordsGiven)
        }
    }

    func testExclusionsSurviveTheDocumentRoundTrip() throws {
        let edit = try SessionEdit.initial(duration: 60)
            .applying(.excludeWords([excluded(word(7, 3, 3.4, "um"))]))

        let data = try JSONEncoder().encode(edit)
        let decoded = try JSONDecoder().decode(SessionEdit.self, from: data)

        XCTAssertEqual(decoded.excludedWords.first?.text, "um")
        XCTAssertEqual(decoded.duration, edit.duration, accuracy: 0.0001)
    }

    func testDocumentsWrittenBeforeWordExclusionsStillLoad() throws {
        // A real edit.json with no `excludedWords` key. It now routes through migration:
        // decoding v1 directly is deliberately refused, so that a *malformed v2* document
        // fails loudly instead of decoding as "nothing was cut" and discarding every edit.
        let json = """
        {"schemaVersion":1,"micTimeOffset":0,
         "clips":[{"source":{"start":0,"end":30}},
                  {"source":{"start":40,"end":60}}],
         "cameraOverlay":[{"t":0,"rect":{"x":0.7,"y":0.7,"width":0.25,"height":0.25},"visible":true}],
         "audioLanes":[{"lane":"microphone","muted":false,"gain":[]}]}
        """

        guard case .migrated(let document) = SessionEditMigration.decode(Data(json.utf8), recordingDuration: 60) else {
            return XCTFail("expected a migration")
        }

        XCTAssertEqual(document.clips.map(\.source), [
            TimeSpan(start: 0, end: 30),
            TimeSpan(start: 40, end: 60)
        ])
        XCTAssertTrue(document.excludedWords.isEmpty)
        XCTAssertEqual(document.duration, 50, accuracy: 0.001)
    }

    // MARK: - Keyframe addressing (the reported failure)

    func testKeyframesWithinAFrameAreTreatedAsOne() throws {
        // Two drags at almost the same playhead produced keyframes at 84.5 and 84.5001, which
        // both displayed as "84.5" and so could not be told apart.
        let a = NormalizedRect(x: 0, y: 0.75, width: 0.25, height: 0.25)
        let b = NormalizedRect(x: 0, y: 0.75, width: 0.19, height: 0.25)

        let edit = try SessionEdit.initial(duration: 300)
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 84.5, rect: a, visible: true)))
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 84.5001, rect: b, visible: true)))

        XCTAssertEqual(edit.cameraOverlay.filter { $0.t > 80 }.count, 1)
        XCTAssertEqual(edit.overlay(at: 84.5)?.rect, b, "the later drag should win")
    }

    func testAKeyframeCanBeRemovedByItsRoundedTime() throws {
        // The agent only ever sees rounded times, so exact matching made this fail with
        // "There is no camera keyframe at 84.50s".
        let edit = try SessionEdit.initial(duration: 300)
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 84.5001, rect: .defaultCameraOverlay, visible: false)))
            .applying(.removeOverlayKeyframe(at: 84.5))

        XCTAssertEqual(edit.cameraOverlay.map(\.t), [0])
    }

    func testRemovingAKeyframeMoreThanAFrameAwayStillFails() {
        XCTAssertThrowsError(try SessionEdit.initial(duration: 300).applying(.removeOverlayKeyframe(at: 84.5))) { error in
            XCTAssertEqual(error as? EditOperationError, .noOverlayKeyframe(at: 84.5))
        }
    }

    func testRemovalPicksTheNearestCandidate() throws {
        let edit = try SessionEdit.initial(duration: 300)
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 10.0, rect: .defaultCameraOverlay, visible: false)))
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 10.05, rect: .defaultCameraOverlay, visible: true)))
            .applying(.removeOverlayKeyframe(at: 10.05))

        XCTAssertEqual(edit.cameraOverlay.map(\.t), [0, 10.0])
    }

    // MARK: - Filler sweeps, resolved locally

    private func fillerTranscript() -> Transcript {
        transcript([
            word(0, 1.0, 1.2, "So"),
            word(1, 1.3, 1.5, "um"),
            word(2, 1.6, 2.0, "today"),
            word(3, 20.0, 20.2, "um"),
            word(4, 20.3, 20.8, "anyway"),
            word(5, 40.0, 40.3, "Um,")
        ])
    }

    func testSweepFindsEveryInstanceInRange() throws {
        let suggestion = AgentRequestResolver.resolveFillerSweep(
            words: ["um"], span: nil, why: nil,
            transcript: fillerTranscript(), micTimeOffset: 0, alreadyExcluded: []
        )

        guard case .excludeWords(let words)? = suggestion?.operation else {
            return XCTFail("expected an exclude_words operation")
        }
        // Matching ignores case and trailing punctuation, so "Um," counts.
        XCTAssertEqual(words.map(\.id), [1, 3, 5])
    }

    func testSweepIsScopedByRange() throws {
        // The user's concern: an unscoped sweep takes out words that mattered.
        let suggestion = AgentRequestResolver.resolveFillerSweep(
            words: ["um"], span: TimeSpan(start: 0, end: 10), why: nil,
            transcript: fillerTranscript(), micTimeOffset: 0, alreadyExcluded: []
        )

        guard case .excludeWords(let words)? = suggestion?.operation else {
            return XCTFail("expected an exclude_words operation")
        }
        XCTAssertEqual(words.map(\.id), [1])
    }

    func testSweepSkipsWordsAlreadyCut() {
        let suggestion = AgentRequestResolver.resolveFillerSweep(
            words: ["um"], span: nil, why: nil,
            transcript: fillerTranscript(), micTimeOffset: 0, alreadyExcluded: [1, 3]
        )

        guard case .excludeWords(let words)? = suggestion?.operation else {
            return XCTFail("expected an exclude_words operation")
        }
        XCTAssertEqual(words.map(\.id), [5])
    }

    func testSweepAppliesTheMicOffsetSoCutsLandOnTheRightFrames() {
        let suggestion = AgentRequestResolver.resolveFillerSweep(
            words: ["um"], span: nil, why: nil,
            transcript: fillerTranscript(), micTimeOffset: 0.4, alreadyExcluded: []
        )

        guard case .excludeWords(let words)? = suggestion?.operation else {
            return XCTFail("expected an exclude_words operation")
        }
        XCTAssertEqual(words.first?.start ?? 0, 1.7, accuracy: 0.0001)
    }

    func testSweepWithNoMatchesProducesNothing() {
        XCTAssertNil(AgentRequestResolver.resolveFillerSweep(
            words: ["pelican"], span: nil, why: nil,
            transcript: fillerTranscript(), micTimeOffset: 0, alreadyExcluded: []
        ))
    }

    func testSweepWithoutATranscriptProducesNothing() {
        XCTAssertNil(AgentRequestResolver.resolveFillerSweep(
            words: ["um"], span: nil, why: nil,
            transcript: nil, micTimeOffset: 0, alreadyExcluded: []
        ))
    }

    // MARK: - Requests parsed out of a reply

    func testTranscriptRequestIsParsedAsARequestNotAnEdit() {
        let reply = """
        I need to see more of the transcript.
        ```json
        [{"op":"request_transcript","from":60,"to":120}]
        ```
        """

        let result = EditSuggestionParser.parse(reply)

        XCTAssertTrue(result.suggestions.isEmpty, "a request is not an applicable edit")
        XCTAssertEqual(result.requests, [.transcript(TimeSpan(start: 60, end: 120))])
    }

    func testFillerSweepIsParsedAsARequest() {
        let reply = #"[{"op":"exclude_filler_words","words":["um","uh"],"from":0,"to":30,"why":"tidy the intro"}]"#

        let result = EditSuggestionParser.parse(reply)

        XCTAssertTrue(result.suggestions.isEmpty)
        XCTAssertEqual(result.requests, [
            .fillerSweep(words: ["um", "uh"], span: TimeSpan(start: 0, end: 30), why: "tidy the intro")
        ])
    }

    func testRequestsAndEditsCanArriveTogether() {
        let reply = """
        ```json
        [{"op":"exclude_words","words":[{"id":1,"start":1.3,"end":1.5,"text":"um"}]},
         {"op":"request_transcript","from":60,"to":90}]
        ```
        """

        let result = EditSuggestionParser.parse(reply)

        XCTAssertEqual(result.suggestions.count, 1)
        XCTAssertEqual(result.requests.count, 1)
    }

    func testMalformedRequestsAreIgnored() {
        for reply in [
            #"[{"op":"request_transcript","from":60}]"#,
            #"[{"op":"request_transcript","from":90,"to":60}]"#,
            #"[{"op":"exclude_filler_words","words":[]}]"#
        ] {
            let result = EditSuggestionParser.parse(reply)
            XCTAssertTrue(result.requests.isEmpty, "reply: \(reply)")
            XCTAssertTrue(result.suggestions.isEmpty, "reply: \(reply)")
        }
    }

    func testExcludeWordsRoundTripsThroughJSON() throws {
        let operation = EditOperation.excludeWords([
            ExcludedWord(id: 1, start: 1.3, end: 1.5, text: "um")
        ])

        let data = try JSONEncoder().encode(operation)
        XCTAssertEqual(try JSONDecoder().decode(EditOperation.self, from: data), operation)

        let json = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(json["op"] as? String, "exclude_words")
    }

    func testRestoreWordsRoundTripsThroughJSON() throws {
        let operation = EditOperation.restoreWords(ids: [1, 2, 3])
        let data = try JSONEncoder().encode(operation)

        XCTAssertEqual(try JSONDecoder().decode(EditOperation.self, from: data), operation)
    }
}
