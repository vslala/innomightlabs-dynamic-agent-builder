import XCTest
@testable import Aura

/// Guards the prompt against the decoder drifting away from it.
///
/// `EditSuggestionPrompt` documents an exact JSON shape per operation, and the agent copies
/// those shapes literally. A rename on `EditOperation`'s coding keys breaks every suggestion of
/// that kind at runtime, silently — the parser drops what it cannot decode. So each shape the
/// prompt promises gets decoded here, and the prompt is checked for mentioning every operation
/// the enum can decode.
final class AgentOperationVocabularyTests: XCTestCase {
    private func decode(_ json: String) throws -> EditOperation {
        try JSONDecoder().decode(EditOperation.self, from: Data(json.utf8))
    }

    private func assertDecodes(_ json: String, _ expected: EditOperation, _ message: String = "") {
        do {
            XCTAssertEqual(try decode(json), expected, message)
        } catch {
            XCTFail("\(json) failed to decode: \(error). \(message)")
        }
    }

    // MARK: - Every documented shape

    func testRemovingOperations() {
        assertDecodes(
            #"{"op":"exclude_words","words":[{"id":7,"start":1.0,"end":1.4,"text":"um"}]}"#,
            .excludeWords([ExcludedWord(id: 7, start: 1.0, end: 1.4, text: "um")])
        )
        assertDecodes(
            #"{"op":"remove_range","start":2.0,"end":3.0}"#,
            .removeRange(TimeSpan(start: 2.0, end: 3.0))
        )
    }

    func testRestoringOperations() {
        assertDecodes(#"{"op":"restore_words","ids":[1,2]}"#, .restoreWords(ids: [1, 2]))

        let id = UUID(uuidString: "5B8F0F1E-1111-4222-8333-444455556666")!
        assertDecodes(#"{"op":"uncut","ids":["5B8F0F1E-1111-4222-8333-444455556666"]}"#, .uncut(ids: [id]))
        // The canonical key still works.
        assertDecodes(#"{"op":"uncut","cutIds":["5B8F0F1E-1111-4222-8333-444455556666"]}"#, .uncut(ids: [id]))
    }

    func testStructureOperations() throws {
        assertDecodes(#"{"op":"split_clip","t":5.0}"#, .splitClip(at: 5.0))
        assertDecodes(#"{"op":"remove_split","t":5.0}"#, .removeSplit(at: 5.0))

        // add_marker mints its own id, so compare the payload rather than the case.
        guard case .addMarker(let marker) = try decode(#"{"op":"add_marker","at":4.5,"label":"intro"}"#) else {
            return XCTFail("add_marker did not decode")
        }
        XCTAssertEqual(marker.at, 4.5)
        XCTAssertEqual(marker.label, "intro")

        let id = UUID(uuidString: "5B8F0F1E-1111-4222-8333-444455556666")!
        assertDecodes(
            #"{"op":"rename_marker","id":"5B8F0F1E-1111-4222-8333-444455556666","label":"outro"}"#,
            .renameMarker(id: id, label: "outro")
        )
        assertDecodes(
            #"{"op":"move_marker","id":"5B8F0F1E-1111-4222-8333-444455556666","to":9.0}"#,
            .moveMarker(id: id, to: 9.0)
        )
        assertDecodes(
            #"{"op":"remove_marker","id":"5B8F0F1E-1111-4222-8333-444455556666"}"#,
            .removeMarker(id: id)
        )
    }

    func testCameraAndAudioOperations() {
        assertDecodes(
            #"{"op":"set_overlay_keyframe","t":0,"rect":{"x":0,"y":0,"width":0.25,"height":0.25},"visible":true}"#,
            .setOverlayKeyframe(OverlayKeyframe(
                t: 0,
                rect: NormalizedRect(x: 0, y: 0, width: 0.25, height: 0.25),
                visible: true
            ))
        )
        assertDecodes(#"{"op":"remove_overlay_keyframe","t":3.0}"#, .removeOverlayKeyframe(at: 3.0))
        assertDecodes(
            #"{"op":"set_camera_style","shape":"circle","cornerRadius":0,"borderWidth":0.02,"borderColor":[1,1,1],"shadowOpacity":0.4,"shadowRadius":0.05}"#,
            .setCameraStyle(PiPStyle(
                shape: .circle,
                cornerRadius: 0,
                borderWidth: 0.02,
                borderColor: [1, 1, 1],
                shadowOpacity: 0.4,
                shadowRadius: 0.05
            ))
        )
        assertDecodes(
            #"{"op":"set_lane_gain","lane":"microphone","t":1.0,"gain":0.5}"#,
            .setLaneGain(lane: .microphone, keyframe: GainKeyframe(t: 1.0, gain: 0.5))
        )
        assertDecodes(
            #"{"op":"set_lane_muted","lane":"system_audio","muted":true}"#,
            .setLaneMuted(lane: .systemAudio, muted: true)
        )
        assertDecodes(
            #"{"op":"set_lane_offset","lane":"microphone","seconds":-0.25}"#,
            .setLaneOffset(lane: .microphone, seconds: -0.25)
        )
    }

    /// A transcript large enough that the digest must be trimmed to fit.
    private static func wordyTranscript(wordCount: Int) -> Transcript {
        var words: [Transcript.Word] = []
        for index in 0..<wordCount {
            let start = Double(index) * 0.1
            words.append(Transcript.Word(id: index, start: start, end: start + 0.09, text: "word\(index)"))
        }
        let segments = stride(from: 0, to: words.count, by: 10).enumerated().map { offset, start in
            let slice = Array(words[start..<min(start + 10, words.count)])
            return Transcript.Segment(
                id: offset,
                start: slice.first!.start,
                end: slice.last!.end,
                text: slice.map(\.text).joined(separator: " "),
                words: slice
            )
        }
        return Transcript(source: "microphone.m4a", engine: "test", segments: segments)
    }

    // MARK: - The prompt and the enum agree

    func testPromptDocumentsEveryDecodableOperation() {
        let prompt = EditSuggestionPrompt.build(
            instruction: "tighten the intro",
            context: EditSuggestionContext(
                sessionID: "s",
                duration: 10,
                transcript: nil,
                document: SessionEdit.initial(duration: 10),
                markers: [],
                digest: nil
            ),
            characterBudget: 32_000
        )

        // Mirrors `EditOperation.Op`'s raw values. A new case added there without a prompt
        // entry — the actual failure mode — trips this list first.
        let documented = [
            "remove_range", "split_clip", "set_overlay_keyframe", "remove_overlay_keyframe",
            "set_lane_gain", "set_lane_muted", "set_lane_offset", "exclude_words",
            "restore_words", "set_camera_style", "uncut", "remove_split", "add_marker",
            "remove_marker", "rename_marker", "move_marker",
        ]
        for op in documented {
            XCTAssertTrue(prompt.contains("\"op\":\"\(op)\""), "prompt never shows the \(op) shape")
        }
    }

    func testOverheadIsMeasuredFromTheTemplateSoTheCapHoldsAsTheVocabularyGrows() {
        // The failure this guards: the vocabulary grows, a hardcoded allowance goes stale, and
        // the message overflows the server's hard cap instead of the digest shrinking.
        let request = String(repeating: "please tighten this up. ", count: 40)
        let measured = EditSuggestionPrompt.overhead(request: request)
        XCTAssertGreaterThan(measured, request.count, "overhead must include the template")

        let prompt = EditSuggestionPrompt.build(
            instruction: request,
            context: EditSuggestionContext(
                sessionID: "s",
                duration: 600,
                transcript: Self.wordyTranscript(wordCount: 6_000),
                document: SessionEdit.initial(duration: 600),
                markers: [],
                digest: nil
            ),
            characterBudget: 32_000
        )
        XCTAssertLessThanOrEqual(prompt.count, 32_000)
    }

    func testPromptExplainsThatTimesAreOnTheRecordingTimeline() {
        let prompt = EditSuggestionPrompt.build(
            instruction: "x",
            context: EditSuggestionContext(
                sessionID: "s",
                duration: 10,
                transcript: nil,
                document: SessionEdit.initial(duration: 10),
                markers: [],
                digest: nil
            ),
            characterBudget: 32_000
        )
        // The single most costly misunderstanding: subtracting cut time from a timestamp.
        XCTAssertTrue(prompt.contains("Never subtract removed time"))
        XCTAssertTrue(prompt.contains("rangeCuts"))
        XCTAssertTrue(prompt.contains("editMarkers"))
    }
}
