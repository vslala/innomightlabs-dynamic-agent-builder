import XCTest
@testable import Aura

final class EditSuggestionTests: XCTestCase {
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

    /// Verbatim output from the live InnomightLabs agent, kept as a fixture so a change to
    /// the parser can't quietly stop understanding what the real agent actually sends.
    func testParsesVerbatimReplyFromTheLiveAgent() {
        let reply = """
        I’d cut the opening false start and hide the camera during the terminal section.

        ```json
        [
          {
            "op": "remove_range",
            "start": 0.0,
            "end": 6.3,
            "why": "Removes the stumbled false start and begins on the clean intro."
          },
          {
            "op": "set_overlay_keyframe",
            "t": 10.0,
            "rect": { "x": 0.72, "y": 0.70, "width": 0.25, "height": 0.25 },
            "visible": false,
            "why": "Hide camera while the terminal is being shown."
          },
          {
            "op": "set_overlay_keyframe",
            "t": 14.5,
            "rect": { "x": 0.72, "y": 0.70, "width": 0.25, "height": 0.25 },
            "visible": true,
            "why": "Restore camera after the terminal segment."
          }
        ]
        ```
        """

        let result = EditSuggestionParser.parse(reply)

        XCTAssertEqual(result.suggestions.count, 3)
        XCTAssertEqual(result.suggestions[0].operation, .removeRange(TimeSpan(start: 0, end: 6.3)))
        XCTAssertEqual(
            result.suggestions[1].operation,
            .setOverlayKeyframe(OverlayKeyframe(
                t: 10,
                rect: NormalizedRect(x: 0.72, y: 0.70, width: 0.25, height: 0.25),
                visible: false
            ))
        )
        XCTAssertEqual(result.suggestions[2].rationale, "Restore camera after the terminal segment.")
        XCTAssertEqual(result.reply, "I’d cut the opening false start and hide the camera during the terminal section.")

        // And every one of them must be applicable to a real document.
        var document = SessionEdit.initial(duration: 54.23)
        for suggestion in result.suggestions {
            document = (try? document.applying(suggestion.operation)) ?? document
        }
        XCTAssertEqual(document.duration, 54.23 - 6.3, accuracy: 0.01)
        XCTAssertEqual(document.overlay(at: 12)?.visible, false)
        XCTAssertEqual(document.overlay(at: 20)?.visible, true)
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

    // MARK: - The A2A envelope
    //
    // Shapes below are copied from real responses from the live agent.

    func testReadsTheReplyFromARealA2AEnvelope() throws {
        let data = Data("""
        {"jsonrpc":"2.0","id":"1","result":{"task":{"id":"b97e4f32","contextId":"aura-A",
         "status":{"state":"TASK_STATE_COMPLETED","message":{"messageId":"ef7337a0","role":"ROLE_AGENT",
         "parts":[{"text":"Here are the proposed edits."}]}},
         "history":[{"messageId":"2da9bcb0","role":"ROLE_USER","parts":[{"text":"the prompt"}],"contextId":"aura-A"}]}}}
        """.utf8)

        // The prompt appears in `history` and is longer, so a naive scavenge would pick it up
        // instead of the answer — the decoder has to read the status message specifically.
        XCTAssertEqual(try InnomightLabsEditSuggester.reply(in: data), "Here are the proposed edits.")
    }

    func testJSONRPCErrorIsSurfacedEvenThoughItArrivesWithHTTP200() {
        let data = Data(#"{"jsonrpc":"2.0","id":"1","error":{"code":-32601,"message":"Unsupported A2A method: message/send"}}"#.utf8)

        XCTAssertThrowsError(try InnomightLabsEditSuggester.reply(in: data)) { error in
            XCTAssertEqual(
                error as? EditSuggestionError,
                .server(status: -32601, detail: "Unsupported A2A method: message/send")
            )
        }
    }

    func testValidationErrorIsSurfaced() {
        let data = Data(#"{"jsonrpc":"2.0","id":"1","error":{"code":-32602,"message":"1 validation error for A2AMessageSendRequest"}}"#.utf8)

        XCTAssertThrowsError(try InnomightLabsEditSuggester.reply(in: data)) { error in
            guard case .server(let status, _)? = error as? EditSuggestionError else {
                return XCTFail("expected a server error")
            }
            XCTAssertEqual(status, -32602)
        }
    }

    func testFailedTaskWithoutAReplyIsAnError() {
        let data = Data(#"{"jsonrpc":"2.0","result":{"task":{"status":{"state":"TASK_STATE_FAILED"}}}}"#.utf8)

        XCTAssertThrowsError(try InnomightLabsEditSuggester.reply(in: data)) { error in
            guard case .server(_, let detail)? = error as? EditSuggestionError else {
                return XCTFail("expected a server error")
            }
            XCTAssertTrue(detail.contains("TASK_STATE_FAILED"))
        }
    }

    func testUnexpectedShapeFallsBackToScavengingText() throws {
        // Defensive: if the task shape ever changes, a reply is better than an error.
        let data = Data(#"{"result":{"something":{"parts":[{"text":"a reply in an unexpected place"}]}}}"#.utf8)

        XCTAssertEqual(try InnomightLabsEditSuggester.reply(in: data), "a reply in an unexpected place")
    }

    func testGarbageResponseThrows() {
        XCTAssertThrowsError(try InnomightLabsEditSuggester.reply(in: Data("not json".utf8))) { error in
            XCTAssertEqual(error as? EditSuggestionError, .unreadableReply)
        }
    }

    // MARK: - The request

    func testRequestBodyMatchesWhatTheServerAccepts() throws {
        // Pinned because the server rejects anything else: PascalCase method names rather than
        // the A2A spec's `message/send`, and `ROLE_USER` rather than `user`.
        let data = try InnomightLabsEditSuggester.rpcBody(prompt: "do the thing", contextID: "aura-session-x")
        let body = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(body["jsonrpc"] as? String, "2.0")
        XCTAssertEqual(body["method"] as? String, "SendMessage")

        let params = try XCTUnwrap(body["params"] as? [String: Any])
        let message = try XCTUnwrap(params["message"] as? [String: Any])
        XCTAssertEqual(message["role"] as? String, "ROLE_USER")
        XCTAssertEqual(message["contextId"] as? String, "aura-session-x")

        let parts = try XCTUnwrap(message["parts"] as? [[String: Any]])
        XCTAssertEqual(parts.count, 1)
        XCTAssertEqual(parts[0]["kind"] as? String, "text")
        XCTAssertEqual(parts[0]["text"] as? String, "do the thing")
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
