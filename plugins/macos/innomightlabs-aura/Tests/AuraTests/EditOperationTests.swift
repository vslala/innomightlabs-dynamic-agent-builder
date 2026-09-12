import XCTest
@testable import Aura

final class EditOperationTests: XCTestCase {
    private func initial(duration: TimeInterval = 30) -> SessionEdit {
        SessionEdit.initial(duration: duration)
    }

    private func spans(_ edit: SessionEdit) -> [TimeSpan] {
        edit.clips.map(\.source)
    }

    // MARK: - JSON contract
    //
    // The agent emits these, so the encoding is a contract. These tests pin the wire shape.

    private func roundTrip(_ operation: EditOperation) throws -> EditOperation {
        let data = try JSONEncoder().encode(operation)
        return try JSONDecoder().decode(EditOperation.self, from: data)
    }

    func testEveryOperationRoundTripsThroughJSON() throws {
        let operations: [EditOperation] = [
            .removeRange(TimeSpan(start: 10, end: 12.5)),
            .splitClip(at: 8),
            .setOverlayKeyframe(OverlayKeyframe(t: 4, rect: .defaultCameraOverlay, visible: false)),
            .removeOverlayKeyframe(at: 4),
            .setLaneGain(lane: .microphone, keyframe: GainKeyframe(t: 2, gain: 0.5)),
            .setLaneMuted(lane: .systemAudio, muted: true)
        ]

        for operation in operations {
            XCTAssertEqual(try roundTrip(operation), operation)
        }
    }

    func testOperationsEncodeFlatFieldsUnderAnOpDiscriminator() throws {
        let data = try JSONEncoder().encode(EditOperation.removeRange(TimeSpan(start: 10, end: 12)))
        let json = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(json["op"] as? String, "remove_range")
        XCTAssertEqual(json["start"] as? Double, 10)
        XCTAssertEqual(json["end"] as? Double, 12)
        XCTAssertNil(json["_0"])
    }

    func testLanesEncodeAsSnakeCaseStrings() throws {
        let data = try JSONEncoder().encode(EditOperation.setLaneMuted(lane: .systemAudio, muted: true))
        let json = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(json["lane"] as? String, "system_audio")
    }

    func testAgentAuthoredJSONDecodes() throws {
        let json = #"{"op":"set_overlay_keyframe","t":130.0,"rect":{"x":0.7,"y":0.7,"width":0.25,"height":0.25}}"#
        let operation = try JSONDecoder().decode(EditOperation.self, from: Data(json.utf8))

        // `visible` is optional on the wire and defaults to true, so the agent only has to
        // send it when hiding the camera.
        XCTAssertEqual(operation, .setOverlayKeyframe(
            OverlayKeyframe(t: 130, rect: NormalizedRect(x: 0.7, y: 0.7, width: 0.25, height: 0.25), visible: true)
        ))
    }

    func testUnknownOperationIsRejected() {
        let json = #"{"op":"reticulate_splines","t":1}"#
        XCTAssertThrowsError(try JSONDecoder().decode(EditOperation.self, from: Data(json.utf8)))
    }

    // MARK: - removeRange

    func testRemovingFromTheMiddleSplitsTheClip() throws {
        let edit = try initial().applying(.removeRange(TimeSpan(start: 10, end: 15)))

        XCTAssertEqual(spans(edit), [TimeSpan(start: 0, end: 10), TimeSpan(start: 15, end: 30)])
    }

    func testRemovingFromTheHeadTrimsRatherThanSplits() throws {
        let edit = try initial().applying(.removeRange(TimeSpan(start: 0, end: 5)))

        XCTAssertEqual(spans(edit), [TimeSpan(start: 5, end: 30)])
    }

    func testRemovingFromTheTailTrimsRatherThanSplits() throws {
        let edit = try initial().applying(.removeRange(TimeSpan(start: 25, end: 30)))

        XCTAssertEqual(spans(edit), [TimeSpan(start: 0, end: 25)])
    }

    func testRemovingSpanningACutAffectsBothClips() throws {
        let edit = try initial()
            .applying(.removeRange(TimeSpan(start: 10, end: 15)))
            .applying(.removeRange(TimeSpan(start: 8, end: 18)))

        XCTAssertEqual(spans(edit), [TimeSpan(start: 0, end: 8), TimeSpan(start: 18, end: 30)])
    }

    func testRemovingTheWholeTimelineIsRejected() {
        XCTAssertThrowsError(try initial().applying(.removeRange(TimeSpan(start: 0, end: 30)))) { error in
            XCTAssertEqual(error as? EditOperationError, .wouldRemoveEntireTimeline)
        }
    }

    func testRemovingAnEmptyRangeIsRejected() {
        XCTAssertThrowsError(try initial().applying(.removeRange(TimeSpan(start: 10, end: 10)))) { error in
            XCTAssertEqual(error as? EditOperationError, .emptyRange)
        }
    }

    func testRemovingARangeThatTouchesNothingIsRejectedRatherThanIgnored() {
        // A stale agent suggestion should surface as an error, not silently do nothing.
        XCTAssertThrowsError(try initial().applying(.removeRange(TimeSpan(start: 40, end: 50)))) { error in
            XCTAssertEqual(error as? EditOperationError, .timeOutsideTimeline(40))
        }
    }

    func testRemovingWithANonFiniteTimeIsRejected() {
        XCTAssertThrowsError(try initial().applying(.removeRange(TimeSpan(start: 0, end: .infinity)))) { error in
            XCTAssertEqual(error as? EditOperationError, .timeNotFinite)
        }
    }

    func testRemovalIsRejectedWithoutMutatingTheDocument() {
        let before = initial()
        let snapshot = before
        _ = try? before.applying(.removeRange(TimeSpan(start: 0, end: 30)))

        XCTAssertEqual(before, snapshot)
    }

    // MARK: - splitClip

    func testSplittingRecordsABoundaryWithoutChangingWhatPlays() throws {
        // A split removes nothing, so it deliberately does not reach the composition: an
        // extra segment would mean an extra insert per track and another boundary at which
        // AVFoundation picks the nearest decodable frame, for identical output.
        let edit = try initial().applying(.splitClip(at: 12))

        XCTAssertEqual(edit.splitPoints, [12])
        XCTAssertEqual(spans(edit), [TimeSpan(start: 0, end: 30)], "the timeline is untouched")
        XCTAssertEqual(edit.duration, 30)
    }

    func testSplittingTwiceAtTheSamePlaceIsRejected() throws {
        let once = try initial().applying(.splitClip(at: 12))

        XCTAssertThrowsError(try once.applying(.splitClip(at: 12))) { error in
            XCTAssertEqual(error as? EditOperationError, .alreadySplit(12))
        }
    }

    func testASplitCanBeRemoved() throws {
        let edit = try initial()
            .applying(.splitClip(at: 12))
            .applying(.removeSplit(at: 12))

        XCTAssertTrue(edit.splitPoints.isEmpty)
    }

    func testRemovingASplitThatIsNotThereIsRejected() {
        XCTAssertThrowsError(try initial().applying(.removeSplit(at: 12))) { error in
            XCTAssertEqual(error as? EditOperationError, .noSplit(at: 12))
        }
    }

    func testSplittingInsideACutIsRejected() throws {
        let edit = try initial().applying(.removeRange(TimeSpan(start: 10, end: 20)))

        XCTAssertThrowsError(try edit.applying(.splitClip(at: 15))) { error in
            XCTAssertEqual(error as? EditOperationError, .noSplitPointInsideAClip(15))
        }
    }

    func testSplittingAtAClipBoundaryIsRejected() {
        XCTAssertThrowsError(try initial().applying(.splitClip(at: 0))) { error in
            XCTAssertEqual(error as? EditOperationError, .noSplitPointInsideAClip(0))
        }
    }

    func testSplittingOutsideTheTimelineIsRejected() {
        XCTAssertThrowsError(try initial().applying(.splitClip(at: 45))) { error in
            XCTAssertEqual(error as? EditOperationError, .noSplitPointInsideAClip(45))
        }
    }

    func testCutsAreIndividuallyAddressable() throws {
        // The reason cuts are stored rather than folded into a clip list: each one can be
        // pointed at and undone on its own, in any order.
        let edit = try initial()
            .applying(.removeRange(TimeSpan(start: 5, end: 8)))
            .applying(.removeRange(TimeSpan(start: 15, end: 18)))
        XCTAssertEqual(edit.cuts.count, 2)

        let first = try XCTUnwrap(edit.cuts.first)
        let restored = try edit.applying(.uncut(ids: [first.id]))

        XCTAssertEqual(restored.cuts.count, 1)
        XCTAssertEqual(spans(restored), [TimeSpan(start: 0, end: 15), TimeSpan(start: 18, end: 30)])
    }

    func testUncuttingSomethingAlreadyGoneIsRejected() {
        XCTAssertThrowsError(try initial().applying(.uncut(ids: [UUID()]))) { error in
            XCTAssertEqual(error as? EditOperationError, .noSuchCut)
        }
    }

    func testOverlappingCutsAreNotMergedInTheDocument() throws {
        // Merging would mean un-cutting the outer range could not re-expose the inner cut.
        let edit = try initial()
            .applying(.excludeWords([ExcludedWord(id: 1, start: 12, end: 12.4, text: "um")]))
            .applying(.removeRange(TimeSpan(start: 10, end: 20)))

        XCTAssertEqual(edit.cuts.count, 2)
        XCTAssertEqual(spans(edit), [TimeSpan(start: 0, end: 10), TimeSpan(start: 20, end: 30)])

        // Restoring only the range leaves the word still cut.
        let rangeCut = try XCTUnwrap(edit.cuts.first { $0.origin == .range })
        let restored = try edit.applying(.uncut(ids: [rangeCut.id]))

        XCTAssertEqual(spans(restored), [TimeSpan(start: 0, end: 12), TimeSpan(start: 12.4, end: 30)])
        XCTAssertTrue(restored.isExcluded(wordID: 1))
    }

    func testTouchingCutsMergeWhenDerivingClips() throws {
        // Adjacent cuts must not leave a zero-length clip between them.
        let edit = try initial()
            .applying(.removeRange(TimeSpan(start: 10, end: 15)))
            .applying(.removeRange(TimeSpan(start: 15, end: 20)))

        XCTAssertEqual(spans(edit), [TimeSpan(start: 0, end: 10), TimeSpan(start: 20, end: 30)])
    }

    // MARK: - overlay keyframes

    func testSettingAKeyframeAtAnExistingTimeReplacesIt() throws {
        let first = NormalizedRect(x: 0.1, y: 0.1, width: 0.2, height: 0.2)
        let second = NormalizedRect(x: 0.5, y: 0.5, width: 0.3, height: 0.3)

        let edit = try initial()
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 10, rect: first, visible: true)))
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 10, rect: second, visible: false)))

        XCTAssertEqual(edit.cameraOverlay.filter { $0.t == 10 }.count, 1)
        XCTAssertEqual(edit.overlay(at: 10)?.rect, second)
        XCTAssertEqual(edit.overlay(at: 10)?.visible, false)
    }

    func testKeyframesAreKeptSorted() throws {
        let edit = try initial()
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 20, rect: .defaultCameraOverlay, visible: false)))
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 10, rect: .defaultCameraOverlay, visible: true)))

        XCTAssertEqual(edit.cameraOverlay.map(\.t), [0, 10, 20])
    }

    func testAZeroSizedOverlayRectIsRejected() {
        let flat = NormalizedRect(x: 0.1, y: 0.1, width: 0, height: 0.2)

        XCTAssertThrowsError(
            try initial().applying(.setOverlayKeyframe(OverlayKeyframe(t: 5, rect: flat, visible: true)))
        ) { error in
            XCTAssertEqual(error as? EditOperationError, .invalidRect)
        }
    }

    func testRemovingAKeyframeThatIsNotThereIsRejected() {
        XCTAssertThrowsError(try initial().applying(.removeOverlayKeyframe(at: 17))) { error in
            XCTAssertEqual(error as? EditOperationError, .noOverlayKeyframe(at: 17))
        }
    }

    func testRemovingTheOnlyKeyframeIsRejected() {
        XCTAssertThrowsError(try initial().applying(.removeOverlayKeyframe(at: 0))) { error in
            XCTAssertEqual(error as? EditOperationError, .wouldRemoveLastOverlayKeyframe)
        }
    }

    func testRemovingAKeyframeLeavesTheOthers() throws {
        let edit = try initial()
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 10, rect: .defaultCameraOverlay, visible: false)))
            .applying(.removeOverlayKeyframe(at: 10))

        XCTAssertEqual(edit.cameraOverlay.map(\.t), [0])
    }

    // MARK: - audio lanes

    func testGainOutsideZeroToOneIsRejected() {
        XCTAssertThrowsError(
            try initial().applying(.setLaneGain(lane: .microphone, keyframe: GainKeyframe(t: 0, gain: 1.5)))
        ) { error in
            XCTAssertEqual(error as? EditOperationError, .gainOutOfRange(1.5))
        }
    }

    func testLanesAreIndependent() throws {
        let edit = try initial()
            .applying(.setLaneMuted(lane: .microphone, muted: true))

        XCTAssertEqual(edit.gain(for: .microphone, at: 0), 0)
        XCTAssertEqual(edit.gain(for: .systemAudio, at: 0), 1)
    }

    func testMutingIsReversible() throws {
        let edit = try initial()
            .applying(.setLaneMuted(lane: .microphone, muted: true))
            .applying(.setLaneMuted(lane: .microphone, muted: false))

        XCTAssertEqual(edit.gain(for: .microphone, at: 0), 1)
    }

    func testGainOnALaneMissingFromTheDocumentAddsIt() throws {
        var edit = initial()
        edit.audioLanes = []

        let updated = try edit.applying(.setLaneGain(lane: .microphone, keyframe: GainKeyframe(t: 0, gain: 0.4)))

        XCTAssertEqual(updated.gain(for: .microphone, at: 0), 0.4)
    }

    // MARK: - interaction with the time map

    func testCuttingRemovesTheContentTheCutNamed() throws {
        let edit = try initial().applying(.removeRange(TimeSpan(start: 10, end: 15)))

        // Composition time 10 now plays what used to be at 15.
        XCTAssertEqual(edit.timeMap.sourceTime(forComposition: 10), 15)
        // And nothing plays the removed range any more.
        XCTAssertEqual(edit.timeMap.compositionTimes(forSource: 12), [])
    }

    func testOverlayKeyframesStayAnchoredToContentAcrossACut() throws {
        // A keyframe authored against session time 20 should still describe that content
        // after an earlier range is cut, just at an earlier playhead position.
        let edit = try initial()
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 20, rect: .defaultCameraOverlay, visible: false)))
            .applying(.removeRange(TimeSpan(start: 5, end: 10)))

        XCTAssertEqual(edit.cameraOverlay.map(\.t), [0, 20])
        XCTAssertEqual(edit.timeMap.compositionTimes(forSource: 20), [15])
    }
}
