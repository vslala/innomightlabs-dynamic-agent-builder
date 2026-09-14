import XCTest
@testable import Aura

final class CameraOverlaySeedTests: XCTestCase {
    private let corner = NormalizedRect.defaultCameraOverlay

    func testNoScreenWindowsProducesOneFullFrameKeyframe() {
        let keyframes = CameraOverlaySeed.keyframes(screenWindows: [], recordingDuration: 100)

        XCTAssertEqual(keyframes, [OverlayKeyframe(t: 0, rect: CameraOverlaySeed.fullFrame, visible: true)])
    }

    /// One screen window in the interior of the recording: full-frame before it, corner
    /// during it, full-frame after — the minimal shape every other case builds on.
    func testOneInteriorWindowProducesFullCornerFull() {
        let keyframes = CameraOverlaySeed.keyframes(
            screenWindows: [TimeSpan(start: 42, end: 70)],
            recordingDuration: 160,
            corner: corner
        )

        XCTAssertEqual(keyframes, [
            OverlayKeyframe(t: 0, rect: CameraOverlaySeed.fullFrame, visible: true),
            OverlayKeyframe(t: 42, rect: corner, visible: true),
            OverlayKeyframe(t: 70, rect: CameraOverlaySeed.fullFrame, visible: true)
        ])
    }

    /// The worked example from the design doc: two disjoint interior windows.
    func testTwoWindowsProduceFiveKeyframes() {
        let keyframes = CameraOverlaySeed.keyframes(
            screenWindows: [TimeSpan(start: 42, end: 70), TimeSpan(start: 95, end: 130)],
            recordingDuration: 160,
            corner: corner
        )

        XCTAssertEqual(keyframes, [
            OverlayKeyframe(t: 0, rect: CameraOverlaySeed.fullFrame, visible: true),
            OverlayKeyframe(t: 42, rect: corner, visible: true),
            OverlayKeyframe(t: 70, rect: CameraOverlaySeed.fullFrame, visible: true),
            OverlayKeyframe(t: 95, rect: corner, visible: true),
            OverlayKeyframe(t: 130, rect: CameraOverlaySeed.fullFrame, visible: true)
        ])
    }

    /// A window touching t=0 must not also get a redundant full-frame keyframe at t=0.
    func testWindowTouchingTheStartEmitsNoRedundantLeadingKeyframe() {
        let keyframes = CameraOverlaySeed.keyframes(
            screenWindows: [TimeSpan(start: 0, end: 50)],
            recordingDuration: 100,
            corner: corner
        )

        XCTAssertEqual(keyframes, [
            OverlayKeyframe(t: 0, rect: corner, visible: true),
            OverlayKeyframe(t: 50, rect: CameraOverlaySeed.fullFrame, visible: true)
        ])
    }

    /// A window reaching the recording's end must not also get a trailing full-frame keyframe.
    func testWindowReachingTheEndEmitsNoTrailingKeyframe() {
        let keyframes = CameraOverlaySeed.keyframes(
            screenWindows: [TimeSpan(start: 50, end: 100)],
            recordingDuration: 100,
            corner: corner
        )

        XCTAssertEqual(keyframes, [
            OverlayKeyframe(t: 0, rect: CameraOverlaySeed.fullFrame, visible: true),
            OverlayKeyframe(t: 50, rect: corner, visible: true)
        ])
    }

    /// A single window spanning the entire recording collapses to just the corner keyframe.
    func testWindowSpanningTheWholeRecordingIsJustTheCornerKeyframe() {
        let keyframes = CameraOverlaySeed.keyframes(
            screenWindows: [TimeSpan(start: 0, end: 100)],
            recordingDuration: 100,
            corner: corner
        )

        XCTAssertEqual(keyframes, [OverlayKeyframe(t: 0, rect: corner, visible: true)])
    }

    func testUnorderedWindowsAreSortedFirst() {
        let ordered = CameraOverlaySeed.keyframes(
            screenWindows: [TimeSpan(start: 95, end: 130), TimeSpan(start: 42, end: 70)],
            recordingDuration: 160,
            corner: corner
        )
        let sorted = CameraOverlaySeed.keyframes(
            screenWindows: [TimeSpan(start: 42, end: 70), TimeSpan(start: 95, end: 130)],
            recordingDuration: 160,
            corner: corner
        )

        XCTAssertEqual(ordered, sorted)
    }

    func testOverlappingWindowsMergeRatherThanDoubleEmit() {
        let keyframes = CameraOverlaySeed.keyframes(
            screenWindows: [TimeSpan(start: 10, end: 50), TimeSpan(start: 30, end: 70)],
            recordingDuration: 100,
            corner: corner
        )

        XCTAssertEqual(keyframes, [
            OverlayKeyframe(t: 0, rect: CameraOverlaySeed.fullFrame, visible: true),
            OverlayKeyframe(t: 10, rect: corner, visible: true),
            OverlayKeyframe(t: 70, rect: CameraOverlaySeed.fullFrame, visible: true)
        ])
    }

    func testZeroDurationRecordingProducesOneFullFrameKeyframe() {
        let keyframes = CameraOverlaySeed.keyframes(screenWindows: [TimeSpan(start: 0, end: 5)], recordingDuration: 0)
        XCTAssertEqual(keyframes, [OverlayKeyframe(t: 0, rect: CameraOverlaySeed.fullFrame, visible: true)])
    }
}
