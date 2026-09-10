import XCTest
@testable import Aura

final class EditSuggestionTests: XCTestCase {
    private func context(
        transcript: Transcript? = nil,
        document: SessionEdit = .initial(duration: 60),
        markers: [(time: TimeInterval, label: String)] = []
    ) -> EditSuggestionContext {
        EditSuggestionContext(
            sessionID: "20260101-120000-aaaa",
            duration: 60,
            transcript: transcript,
            document: document,
            markers: markers
        )
    }

    private func transcript(_ cues: [(TimeInterval, TimeInterval, String)]) -> Transcript {
        Transcript(
            source: "microphone.m4a",
            engine: "test",
            language: "en",
            segments: cues.enumerated().map { index, cue in
                Transcript.Segment(id: index, start: cue.0, end: cue.1, text: cue.2, words: nil)
            }
        )
    }

    // MARK: - Prompt

    func testPromptDeclaresEveryOperationTheParserAccepts() {
        let prompt = EditSuggestionPrompt.build(instruction: "tidy this up", context: context())

        for op in ["remove_range", "split_clip", "set_overlay_keyframe", "remove_overlay_keyframe",
                   "set_lane_gain", "set_lane_muted", "set_lane_offset"] {
            XCTAssertTrue(prompt.contains(op), "the agent isn't told about \(op)")
        }
    }

    func testPromptIncludesTheInstructionAndTheDuration() {
        let prompt = EditSuggestionPrompt.build(instruction: "cut the stumble", context: context())

        XCTAssertTrue(prompt.contains("cut the stumble"))
        XCTAssertTrue(prompt.contains("60.00s"))
    }

    func testPromptDescribesTheCurrentEditNotJustTheRecording() throws {
        // Otherwise the agent proposes edits against content that is no longer there.
        let document = try SessionEdit.initial(duration: 60)
            .applying(.removeRange(TimeSpan(start: 10, end: 20)))
            .applying(.setLaneMuted(lane: .systemAudio, muted: true))

        let prompt = EditSuggestionPrompt.build(instruction: "what next", context: context(document: document))

        XCTAssertTrue(prompt.contains("0.00-10.00"))
        XCTAssertTrue(prompt.contains("20.00-60.00"))
        XCTAssertTrue(prompt.contains("system_audio: muted"))
    }

    func testTranscriptTimesAreShiftedIntoRecordingTime() {
        // The transcript is stamped in the microphone file's clock; operations are in
        // recording time. Handing over the unshifted numbers would make every AI cut land
        // slightly wrong.
        let document = SessionEdit.initial(duration: 60, micTimeOffset: 0.5)
        let prompt = EditSuggestionPrompt.build(
            instruction: "cut the first bit",
            context: context(transcript: transcript([(10, 12, "hello there")]), document: document)
        )

        XCTAssertTrue(prompt.contains("10.50-12.50 hello there"), "expected mic offset applied")
        XCTAssertFalse(prompt.contains("10.00-12.00 hello there"))
    }

    func testPromptSaysWhenThereIsNoTranscript() {
        let prompt = EditSuggestionPrompt.build(instruction: "help", context: context())
        XCTAssertTrue(prompt.contains("Transcript: not available"))
    }

    func testPromptIncludesMarkers() {
        let prompt = EditSuggestionPrompt.build(
            instruction: "cut what I flagged",
            context: context(markers: [(time: 42, label: "mistake")])
        )
        XCTAssertTrue(prompt.contains("42.00: mistake"))
    }

    func testVeryLongTranscriptIsTruncatedAndSaysSo() {
        let cues = (0..<600).map { (Double($0), Double($0) + 0.5, "cue \($0)") }
        let prompt = EditSuggestionPrompt.build(
            instruction: "summarise",
            context: context(transcript: transcript(cues))
        )

        XCTAssertTrue(prompt.contains("further cues omitted"))
        XCTAssertFalse(prompt.contains("cue 599"))
    }

    // MARK: - Parsing

    func testParsesFencedJSONAndKeepsTheProse() {
        let reply = """
        I'd cut the stumble around ten seconds.

        ```json
        [{"op":"remove_range","start":10.0,"end":12.5,"why":"repeated sentence"}]
        ```
        """

        let result = EditSuggestionParser.parse(reply)

        XCTAssertEqual(result.suggestions.count, 1)
        XCTAssertEqual(result.suggestions[0].operation, .removeRange(TimeSpan(start: 10, end: 12.5)))
        XCTAssertEqual(result.suggestions[0].rationale, "repeated sentence")
        XCTAssertEqual(result.reply, "I'd cut the stumble around ten seconds.")
    }

    func testParsesBareJSONArrayWithSurroundingProse() {
        let reply = """
        Here you go:
        [{"op":"set_lane_muted","lane":"system_audio","muted":true}]
        Let me know.
        """

        let result = EditSuggestionParser.parse(reply)

        XCTAssertEqual(result.suggestions.map(\.operation), [.setLaneMuted(lane: .systemAudio, muted: true)])
        XCTAssertTrue(result.reply.contains("Here you go"))
        XCTAssertTrue(result.reply.contains("Let me know"))
    }

    func testParsesAnOperationsWrapperObject() {
        let reply = #"{"operations":[{"op":"split_clip","t":8.0}]}"#

        XCTAssertEqual(
            EditSuggestionParser.parse(reply).suggestions.map(\.operation),
            [.splitClip(at: 8)]
        )
    }

    func testParsesASingleBareOperationObject() {
        let reply = #"{"op":"set_lane_offset","lane":"microphone","seconds":-0.3}"#

        XCTAssertEqual(
            EditSuggestionParser.parse(reply).suggestions.map(\.operation),
            [.setLaneOffset(lane: .microphone, seconds: -0.3)]
        )
    }

    func testParsesMultipleOperationsPreservingOrder() {
        let reply = """
        ```json
        [{"op":"remove_range","start":1,"end":2},
         {"op":"set_lane_muted","lane":"microphone","muted":true},
         {"op":"split_clip","t":9}]
        ```
        """

        XCTAssertEqual(EditSuggestionParser.parse(reply).suggestions.map(\.operation), [
            .removeRange(TimeSpan(start: 1, end: 2)),
            .setLaneMuted(lane: .microphone, muted: true),
            .splitClip(at: 9)
        ])
    }

    func testUnknownOperationsAreDroppedRatherThanFailingTheWholeReply() {
        // A suggestion the app can't represent must not take the valid ones down with it.
        let reply = """
        ```json
        [{"op":"reticulate_splines","t":1},
         {"op":"remove_range","start":3,"end":4}]
        ```
        """

        let result = EditSuggestionParser.parse(reply)

        XCTAssertEqual(result.suggestions.map(\.operation), [.removeRange(TimeSpan(start: 3, end: 4))])
    }

    func testPlainRefusalYieldsNoSuggestionsButKeepsTheReply() {
        let reply = "I can't tell which part you mean — could you point at a timestamp?"

        let result = EditSuggestionParser.parse(reply)

        XCTAssertTrue(result.suggestions.isEmpty)
        XCTAssertEqual(result.reply, reply)
    }

    func testEmptyArrayYieldsNoSuggestions() {
        let result = EditSuggestionParser.parse("Nothing needs changing.\n```json\n[]\n```")

        XCTAssertTrue(result.suggestions.isEmpty)
        XCTAssertEqual(result.reply, "Nothing needs changing.")
    }

    func testBracketsInsideStringsDoNotConfuseTheScanner() {
        let reply = #"[{"op":"remove_range","start":1,"end":2,"why":"he says [inaudible] here"}]"#

        let result = EditSuggestionParser.parse(reply)

        XCTAssertEqual(result.suggestions.count, 1)
        XCTAssertEqual(result.suggestions[0].rationale, "he says [inaudible] here")
    }

    func testMalformedJSONYieldsNoSuggestionsRatherThanCrashing() {
        for reply in ["[{\"op\":", "```json\n{oh no\n```", "[[[", "{}"] {
            XCTAssertTrue(EditSuggestionParser.parse(reply).suggestions.isEmpty, "reply: \(reply)")
        }
    }

    func testRationaleIsOptional() {
        let reply = #"[{"op":"split_clip","t":5}]"#

        XCTAssertNil(EditSuggestionParser.parse(reply).suggestions.first?.rationale)
    }

    // MARK: - Server error shapes

    func testFastAPIStringDetailIsSurfaced() {
        let data = Data(#"{"detail":"Agent2Agent sharing is not enabled"}"#.utf8)

        XCTAssertEqual(
            InnomightLabsEditSuggester.detail(in: data),
            "Agent2Agent sharing is not enabled"
        )
    }

    func testFastAPIValidationDetailIsSurfaced() {
        let data = Data(#"{"detail":[{"msg":"field required"},{"msg":"bad id"}]}"#.utf8)

        XCTAssertEqual(InnomightLabsEditSuggester.detail(in: data), "field required; bad id")
    }

    // MARK: - Finding the reply in an A2A task

    func testTextPartsAreFoundWhereverTheTaskPutThem() {
        let data = Data("""
        {"id":"t1","status":{"state":"completed","message":{"parts":[{"kind":"text","text":"short"}]}},
         "artifacts":[{"parts":[{"kind":"text","text":"the substantive reply with operations"}]}]}
        """.utf8)

        let parts = InnomightLabsEditSuggester.textParts(in: data)

        // Longest first, since the substantive answer is the long one.
        XCTAssertEqual(parts.first, "the substantive reply with operations")
        XCTAssertTrue(parts.contains("short"))
    }

    func testNonTextPartsAreIgnored() {
        let data = Data(#"{"artifacts":[{"parts":[{"kind":"file","uri":"x"}]}]}"#.utf8)

        XCTAssertTrue(InnomightLabsEditSuggester.textParts(in: data).isEmpty)
    }

    func testGarbageResponseYieldsNoTextParts() {
        XCTAssertTrue(InnomightLabsEditSuggester.textParts(in: Data("not json".utf8)).isEmpty)
    }

    // MARK: - Summaries shown in the suggestion list

    func testEveryOperationHasAReadableSummary() {
        let operations: [EditOperation] = [
            .removeRange(TimeSpan(start: 10, end: 12)),
            .splitClip(at: 8),
            .setOverlayKeyframe(OverlayKeyframe(t: 4, rect: .defaultCameraOverlay, visible: false)),
            .removeOverlayKeyframe(at: 4),
            .setLaneGain(lane: .microphone, keyframe: GainKeyframe(t: 2, gain: 0.5)),
            .setLaneMuted(lane: .systemAudio, muted: true),
            .setLaneOffset(lane: .microphone, seconds: -0.3)
        ]

        for operation in operations {
            let summary = EditOperationDescription.summary(operation)
            XCTAssertFalse(summary.isEmpty)
            XCTAssertFalse(summary.contains("Aura."), "summary leaks a type name: \(summary)")
        }
    }

    func testHideAndMoveReadDifferently() {
        let hide = EditOperationDescription.summary(
            .setOverlayKeyframe(OverlayKeyframe(t: 130, rect: .defaultCameraOverlay, visible: false))
        )
        let move = EditOperationDescription.summary(
            .setOverlayKeyframe(OverlayKeyframe(t: 130, rect: .defaultCameraOverlay, visible: true))
        )

        XCTAssertTrue(hide.localizedCaseInsensitiveContains("hide"))
        XCTAssertTrue(move.localizedCaseInsensitiveContains("move"))
    }
}
