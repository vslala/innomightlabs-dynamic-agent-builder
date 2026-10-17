import XCTest
import CoreMedia
@testable import Aura

final class SpeechReplacementTests: XCTestCase {
    private func initial(duration: TimeInterval = 30) -> SessionEdit {
        SessionEdit.initial(duration: duration)
    }

    private func replacement(
        _ start: TimeInterval = 10,
        _ end: TimeInterval = 14,
        text: String = "A better sentence.",
        duration: TimeInterval? = nil,
        id: UUID = UUID()
    ) -> SpeechReplacement {
        SpeechReplacement(
            id: id,
            span: TimeSpan(start: start, end: end),
            text: text,
            originalText: "the old one",
            duration: duration ?? (end - start)
        )
    }

    // MARK: - The edit

    func testReplacingSpeechStoresTheSelectionAndKeepsItSorted() throws {
        let edit = try initial()
            .applying(.replaceSpeech(replacement(20, 24)))
            .applying(.replaceSpeech(replacement(5, 8)))

        XCTAssertEqual(edit.speechReplacements.map(\.span.start), [5, 20])
    }

    func testTextIsTrimmedAndTimesAreSnapped() throws {
        let edit = try initial().applying(.replaceSpeech(replacement(10.0000001, 14, text: "  hello  ")))

        XCTAssertEqual(edit.speechReplacements.first?.text, "hello")
        XCTAssertEqual(try XCTUnwrap(edit.speechReplacements.first).span.start, 10, accuracy: 0.0001)
    }

    func testAReplacementWithoutAudioCannotBeApplied() {
        // An agent suggests a draft; accepting it renders first. The document must never
        // describe speech that does not exist.
        let draft = SpeechReplacement(span: TimeSpan(start: 1, end: 3), text: "x")
        XCTAssertThrowsError(try initial().applying(.replaceSpeech(draft))) {
            XCTAssertEqual($0 as? EditOperationError, .speechNotRendered)
        }
    }

    func testRejectsEmptyTextTooShortAndOutsideTheRecording() {
        XCTAssertThrowsError(try initial().applying(.replaceSpeech(replacement(text: "   ")))) {
            XCTAssertEqual($0 as? EditOperationError, .emptySpeechText)
        }
        XCTAssertThrowsError(try initial().applying(.replaceSpeech(replacement(10, 10.1)))) {
            XCTAssertEqual($0 as? EditOperationError, .speechSpanTooShort)
        }
        XCTAssertThrowsError(try initial().applying(.replaceSpeech(replacement(28, 33)))) {
            XCTAssertEqual($0 as? EditOperationError, .timeOutsideTimeline(33))
        }
    }

    func testReplacementsCannotOverlapButCanTouch() throws {
        let edit = try initial().applying(.replaceSpeech(replacement(10, 14)))

        XCTAssertThrowsError(try edit.applying(.replaceSpeech(replacement(13, 16)))) {
            XCTAssertEqual($0 as? EditOperationError, .speechOverlaps)
        }
        XCTAssertNoThrow(try edit.applying(.replaceSpeech(replacement(14, 16))))
    }

    func testReplacingTheSameIdAgainSwapsItInsteadOfOverlapping() throws {
        let id = UUID()
        let edit = try initial()
            .applying(.replaceSpeech(replacement(10, 14, text: "first", id: id)))
            .applying(.replaceSpeech(replacement(10, 14, text: "second", id: id)))

        XCTAssertEqual(edit.speechReplacements.map(\.text), ["second"])
    }

    func testClipShorterThanTheSelectionIsStoredAsTheSelectionLength() throws {
        // Shorter speech is padded to fit, so the clip is never shorter than its span.
        let edit = try initial().applying(.replaceSpeech(replacement(10, 14, duration: 2)))

        XCTAssertEqual(try XCTUnwrap(edit.speechReplacements.first).duration, 4, accuracy: 0.0001)
        XCTAssertEqual(try XCTUnwrap(edit.speechReplacements.first).hold, 0)
    }

    func testALongHoldIsAllowedButARunawayOneIsRejected() throws {
        // Past the UI's confirmation threshold is the user's call to make.
        XCTAssertNoThrow(try initial().applying(.replaceSpeech(replacement(10, 12, duration: 20))))

        XCTAssertThrowsError(try initial().applying(.replaceSpeech(replacement(10, 12, duration: 73)))) {
            XCTAssertEqual($0 as? EditOperationError, .speechHoldTooLong(71))
        }
    }

    func testRestoringBringsTheOriginalBackAndUnknownIdsAreRefused() throws {
        let a = replacement(2, 5), b = replacement(10, 14)
        let edit = try initial()
            .applying(.replaceSpeech(a))
            .applying(.replaceSpeech(b))

        let restored = try edit.applying(.restoreSpeech(ids: [a.id, b.id]))
        XCTAssertTrue(restored.speechReplacements.isEmpty)
        XCTAssertEqual(restored.duration, 30)

        XCTAssertThrowsError(try initial().applying(.restoreSpeech(ids: [UUID()]))) {
            XCTAssertEqual($0 as? EditOperationError, .noSuchSpeech)
        }
    }

    // MARK: - Wire format

    func testOperationsRoundTripThroughJSON() throws {
        let operations: [EditOperation] = [
            .replaceSpeech(replacement(10, 14, duration: 6)),
            .restoreSpeech(ids: [UUID(), UUID()])
        ]
        for operation in operations {
            let decoded = try JSONDecoder().decode(EditOperation.self, from: JSONEncoder().encode(operation))
            XCTAssertEqual(decoded, operation)
        }
    }

    func testTheAgentCanProposeAReplacementWithOnlyTimesAndText() throws {
        let json = #"{"op":"replace_speech","start":26.56,"end":34.7,"text":"I build InnomightLabs."}"#
        let decoded = try JSONDecoder().decode(EditOperation.self, from: Data(json.utf8))

        guard case .replaceSpeech(let draft) = decoded else { return XCTFail("wrong operation: \(decoded)") }
        XCTAssertTrue(draft.isDraft)
        XCTAssertEqual(draft.text, "I build InnomightLabs.")
        XCTAssertEqual(draft.span, TimeSpan(start: 26.56, end: 34.7))
    }

    func testReplacementsSurviveSavingAndOldDocumentsStillLoad() throws {
        let edit = try initial().applying(.replaceSpeech(replacement(10, 14, duration: 6)))
        let reloaded = try JSONDecoder().decode(SessionEdit.self, from: JSONEncoder().encode(edit))
        XCTAssertEqual(reloaded.speechReplacements, edit.speechReplacements)

        // A document written before replacements existed has no such key.
        var object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(initial())) as? [String: Any]
        )
        object.removeValue(forKey: "speechReplacements")
        let old = try JSONDecoder().decode(SessionEdit.self, from: JSONSerialization.data(withJSONObject: object))
        XCTAssertTrue(old.speechReplacements.isEmpty)
    }

    // MARK: - The timeline it produces

    func testSpeechThatRunsLongHoldsThePictureAndLengthensTheTimeline() throws {
        let edit = try initial().applying(.replaceSpeech(replacement(10, 14, duration: 7)))

        XCTAssertEqual(edit.duration, 33, accuracy: 0.001)

        let segments = edit.timeMap.segments
        XCTAssertEqual(segments.map(\.isHold), [false, true, false])
        let hold = segments[1]
        XCTAssertEqual(Timeline.seconds(hold.composition.start), 14, accuracy: 0.001)
        XCTAssertEqual(Timeline.seconds(hold.composition.duration), 3, accuracy: 0.001)
        XCTAssertEqual(Timeline.seconds(hold.source.start), 14, accuracy: 0.001)
    }

    func testEverythingAfterAHoldMovesLaterInCompositionButNotInSession() throws {
        let map = try initial().applying(.replaceSpeech(replacement(10, 14, duration: 7))).timeMap

        XCTAssertEqual(try XCTUnwrap(map.sourceTime(forComposition: 20.0)), 17, accuracy: 0.001)
        XCTAssertEqual(try XCTUnwrap(map.compositionTimes(forSource: 20.0).first), 23, accuracy: 0.001)
    }

    func testThroughoutAHoldTheRecordingStaysOnOneInstant() throws {
        let map = try initial().applying(.replaceSpeech(replacement(10, 14, duration: 7))).timeMap

        for composition in [14.0, 15.5, 16.99] {
            XCTAssertEqual(try XCTUnwrap(map.sourceTime(forComposition: composition)), 14, accuracy: 0.001)
        }
    }

    func testSpeechThatFitsAddsNoHold() throws {
        let edit = try initial().applying(.replaceSpeech(replacement(10, 14, duration: 4)))

        XCTAssertEqual(edit.duration, 30)
        XCTAssertFalse(edit.timeMap.segments.contains(where: \.isHold))
    }

    func testAHoldWhoseInstantWasCutAwayDisappears() throws {
        // The span's last instant sits inside a later cut, so there is no picture to hold.
        let edit = try initial()
            .applying(.replaceSpeech(replacement(10, 14, duration: 7)))
            .applying(.removeRange(TimeSpan(start: 13, end: 20)))

        XCTAssertFalse(edit.timeMap.segments.contains(where: \.isHold))
        XCTAssertEqual(edit.duration, 23, accuracy: 0.001)
    }

    func testACutRightAfterTheSpanLeavesTheHoldInPlace() throws {
        let edit = try initial()
            .applying(.replaceSpeech(replacement(10, 14, duration: 7)))
            .applying(.removeRange(TimeSpan(start: 14, end: 20)))

        XCTAssertEqual(edit.timeMap.segments.map(\.isHold), [false, true, false])
        XCTAssertEqual(edit.duration, 27, accuracy: 0.001)
    }

    func testAMarkerAfterTheHoldIsStillReachable() throws {
        let map = try initial().applying(.replaceSpeech(replacement(10, 14, duration: 7))).timeMap
        XCTAssertEqual(map.compositionTimes(forSource: 25).count, 1)
        XCTAssertTrue(map.compositionTimes(forSource: 14.0).isEmpty == false)
    }

    // MARK: - Undo

    @MainActor
    func testReplacingIsOneUndoStep() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-speech-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = EditDocumentStore.load(folder: SessionFolder.load(rootURL: root), duration: 30, micTimeOffset: 0)

        XCTAssertTrue(store.apply(.replaceSpeech(replacement(10, 14, duration: 7))))
        XCTAssertEqual(store.document.duration, 33, accuracy: 0.001)

        store.undo()
        XCTAssertEqual(store.document.duration, 30)
        XCTAssertTrue(store.document.speechReplacements.isEmpty)
    }
}
