import XCTest
@testable import Aura

/// Layout modes are expressed purely as camera-overlay keyframes, so they must round-trip:
/// whatever `keyframe(at:defaultRect:)` produces has to classify back to the same mode, or the
/// menu would show the wrong thing as current.
final class LayoutModeTests: XCTestCase {
    private let pip = NormalizedRect(x: 0.7, y: 0.7, width: 0.25, height: 0.25)

    func testModesRoundTrip() {
        for mode in LayoutMode.allCases {
            let keyframe = mode.keyframe(at: 5, defaultRect: pip)
            XCTAssertEqual(LayoutMode.mode(of: keyframe), mode, "\(mode.title) did not round-trip")
        }
    }

    func testScreenOnlyHidesTheCamera() {
        XCTAssertFalse(LayoutMode.screenOnly.keyframe(at: 0, defaultRect: pip).visible)
    }

    func testCameraOnlyFillsTheFrame() {
        let rect = LayoutMode.cameraOnly.keyframe(at: 0, defaultRect: pip).rect
        XCTAssertEqual(rect.x, 0, accuracy: 0.0001)
        XCTAssertEqual(rect.y, 0, accuracy: 0.0001)
        XCTAssertEqual(rect.width, 1, accuracy: 0.0001)
        XCTAssertEqual(rect.height, 1, accuracy: 0.0001)
    }

    func testScreenAndCameraKeepsTheGivenRect() {
        let keyframe = LayoutMode.screenAndCamera.keyframe(at: 0, defaultRect: pip)
        XCTAssertEqual(keyframe.rect, pip)
        XCTAssertTrue(keyframe.visible)
    }

    func testKeyframeTimeIsCarriedThrough() {
        // A mode change applies from the playhead onwards, so the time must survive.
        for mode in LayoutMode.allCases {
            XCTAssertEqual(mode.keyframe(at: 42.5, defaultRect: pip).t, 42.5, accuracy: 0.0001)
        }
    }

    func testNoOverlayReadsAsScreenOnly() {
        XCTAssertEqual(LayoutMode.mode(of: nil), .screenOnly)
    }

    func testAHiddenFullFrameCameraIsStillScreenOnly() {
        let hidden = OverlayKeyframe(
            t: 0,
            rect: NormalizedRect(x: 0, y: 0, width: 1, height: 1),
            visible: false
        )
        XCTAssertEqual(LayoutMode.mode(of: hidden), .screenOnly)
    }

    func testANearlyFullFrameCameraCountsAsCameraOnly() {
        // Rounding through JSON must not flip the classification.
        let nearly = OverlayKeyframe(
            t: 0,
            rect: NormalizedRect(x: 0.005, y: 0.005, width: 0.99, height: 0.99),
            visible: true
        )
        XCTAssertEqual(LayoutMode.mode(of: nearly), .cameraOnly)
    }
}
