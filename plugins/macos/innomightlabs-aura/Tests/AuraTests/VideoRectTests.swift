import XCTest
@testable import Aura

/// The player letterboxes under `resizeAspect`, so subtitles and camera handles have to be
/// placed against the picture rather than the container. Getting this wrong drifts the subtitle
/// off the image as the window's aspect changes — which is why it is pinned.
final class VideoRectTests: XCTestCase {
    private let widescreen = CGSize(width: 1920, height: 1080)

    func testExactAspectFillsTheContainer() {
        let rect = VideoRect.fitted(renderSize: widescreen, in: CGSize(width: 640, height: 360))
        XCTAssertEqual(rect, CGRect(x: 0, y: 0, width: 640, height: 360))
    }

    func testTallContainerLetterboxesTopAndBottom() {
        // 16:9 video in a square container: full width, bars above and below.
        let rect = VideoRect.fitted(renderSize: widescreen, in: CGSize(width: 400, height: 400))
        XCTAssertEqual(rect.width, 400, accuracy: 0.001)
        XCTAssertEqual(rect.height, 225, accuracy: 0.001)
        XCTAssertEqual(rect.minX, 0, accuracy: 0.001)
        XCTAssertEqual(rect.minY, 87.5, accuracy: 0.001)
    }

    func testWideContainerPillarboxesLeftAndRight() {
        let rect = VideoRect.fitted(renderSize: widescreen, in: CGSize(width: 1000, height: 200))
        XCTAssertEqual(rect.width, 355.5555, accuracy: 0.01)
        XCTAssertEqual(rect.height, 200, accuracy: 0.001)
        XCTAssertEqual(rect.minY, 0, accuracy: 0.001)
        XCTAssertEqual(rect.midX, 500, accuracy: 0.001)
    }

    func testThePictureIsAlwaysCentred() {
        for container in [CGSize(width: 400, height: 400),
                          CGSize(width: 1000, height: 200),
                          CGSize(width: 137, height: 941)] {
            let rect = VideoRect.fitted(renderSize: widescreen, in: container)
            XCTAssertEqual(rect.midX, container.width / 2, accuracy: 0.001)
            XCTAssertEqual(rect.midY, container.height / 2, accuracy: 0.001)
        }
    }

    func testAspectRatioIsPreserved() {
        for container in [CGSize(width: 400, height: 400), CGSize(width: 1000, height: 200)] {
            let rect = VideoRect.fitted(renderSize: widescreen, in: container)
            XCTAssertEqual(rect.width / rect.height, 16.0 / 9, accuracy: 0.001)
        }
    }

    func testThePictureNeverExceedsTheContainer() {
        for container in [CGSize(width: 400, height: 400), CGSize(width: 1000, height: 200)] {
            let rect = VideoRect.fitted(renderSize: widescreen, in: container)
            XCTAssertLessThanOrEqual(rect.width, container.width + 0.001)
            XCTAssertLessThanOrEqual(rect.height, container.height + 0.001)
        }
    }

    func testPortraitVideo() {
        let rect = VideoRect.fitted(
            renderSize: CGSize(width: 1080, height: 1920),
            in: CGSize(width: 400, height: 400)
        )
        XCTAssertEqual(rect.width, 225, accuracy: 0.001)
        XCTAssertEqual(rect.height, 400, accuracy: 0.001)
    }

    /// Degenerate inputs fall back to the container rather than producing NaN, which would
    /// propagate into a `.position` modifier and blank the overlay.
    func testDegenerateSizesFallBackToTheContainer() {
        let container = CGSize(width: 320, height: 240)
        for render in [CGSize.zero,
                       CGSize(width: 0, height: 100),
                       CGSize(width: 100, height: 0)] {
            let rect = VideoRect.fitted(renderSize: render, in: container)
            XCTAssertEqual(rect, CGRect(origin: .zero, size: container))
        }
        XCTAssertEqual(
            VideoRect.fitted(renderSize: widescreen, in: .zero),
            CGRect(origin: .zero, size: .zero)
        )
    }
}
