import XCTest
@testable import Aura

final class SessionEditTests: XCTestCase {
    private func initial(duration: TimeInterval = 30) -> SessionEdit {
        SessionEdit.initial(duration: duration)
    }

    func testInitialDocumentIsOneClipSpanningTheRecording() {
        let edit = initial()

        XCTAssertEqual(edit.schemaVersion, SessionEdit.currentSchemaVersion)
        XCTAssertEqual(edit.clips.count, 1)
        XCTAssertEqual(edit.clips[0].source, TimeSpan(start: 0, end: 30))
        XCTAssertEqual(edit.duration, 30)
    }

    func testInitialDocumentAlwaysHasAnOverlayKeyframeAtZero() {
        // Without one, AVFoundation holds the camera layer at the identity transform and
        // renders it full-size over the screen until the first keyframe.
        XCTAssertEqual(initial().cameraOverlay.first?.t, 0)
    }

    func testInitialDocumentHasBothAudioLanesAtUnityGain() {
        let edit = initial()

        XCTAssertEqual(edit.audioLanes.map(\.lane), AudioLane.allCases)
        XCTAssertEqual(edit.gain(for: .microphone, at: 0), 1)
        XCTAssertEqual(edit.gain(for: .systemAudio, at: 12), 1)
    }

    func testRoundTripsThroughJSON() throws {
        var edit = initial()
        edit.micTimeOffset = 0.184
        edit = try edit.applying(.removeRange(TimeSpan(start: 10, end: 12)))
        edit = try edit.applying(.setOverlayKeyframe(
            OverlayKeyframe(t: 5, rect: NormalizedRect(x: 0.1, y: 0.1, width: 0.3, height: 0.2), visible: false)
        ))
        edit = try edit.applying(.setLaneMuted(lane: .systemAudio, muted: true))

        let data = try JSONEncoder().encode(edit)
        XCTAssertEqual(try JSONDecoder().decode(SessionEdit.self, from: data), edit)
    }

    func testMicTimeOffsetSurvivesTheRoundTrip() throws {
        var edit = initial()
        edit.micTimeOffset = 0.184

        let data = try JSONEncoder().encode(edit)
        let decoded = try JSONDecoder().decode(SessionEdit.self, from: data)

        XCTAssertEqual(decoded.micTimeOffset, 0.184)
    }

    func testOverlayLookupHoldsTheLastKeyframeUntilTheNext() throws {
        let hidden = NormalizedRect(x: 0.5, y: 0.5, width: 0.2, height: 0.2)
        let edit = try initial()
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 10, rect: hidden, visible: false)))

        XCTAssertEqual(edit.overlay(at: 0)?.visible, true)
        XCTAssertEqual(edit.overlay(at: 9.9)?.visible, true)
        XCTAssertEqual(edit.overlay(at: 10)?.visible, false)
        XCTAssertEqual(edit.overlay(at: 25)?.visible, false)
    }

    func testOverlayLookupBeforeTheFirstKeyframeFallsBackRatherThanReturningNil() {
        var edit = initial()
        edit.cameraOverlay = [OverlayKeyframe(t: 12, rect: .defaultCameraOverlay, visible: true)]

        XCTAssertNotNil(edit.overlay(at: 0))
    }

    func testMutedLaneReportsZeroGainRegardlessOfKeyframes() throws {
        let edit = try initial()
            .applying(.setLaneGain(lane: .microphone, keyframe: GainKeyframe(t: 0, gain: 0.8)))
            .applying(.setLaneMuted(lane: .microphone, muted: true))

        XCTAssertEqual(edit.gain(for: .microphone, at: 0), 0)
    }

    func testGainKeyframesHoldUntilTheNext() throws {
        let edit = try initial()
            .applying(.setLaneGain(lane: .systemAudio, keyframe: GainKeyframe(t: 10, gain: 0.25)))

        XCTAssertEqual(edit.gain(for: .systemAudio, at: 5), 1)
        XCTAssertEqual(edit.gain(for: .systemAudio, at: 10), 0.25)
        XCTAssertEqual(edit.gain(for: .systemAudio, at: 29), 0.25)
    }

    func testDurationShrinksByWhatWasRemoved() throws {
        let edit = try initial().applying(.removeRange(TimeSpan(start: 10, end: 15)))
        XCTAssertEqual(edit.duration, 25)
    }
}
