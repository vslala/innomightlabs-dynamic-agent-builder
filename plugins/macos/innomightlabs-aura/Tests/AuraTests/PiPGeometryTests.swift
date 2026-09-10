import XCTest
import AVFoundation
@testable import Aura

final class PiPGeometryTests: XCTestCase {
    private let camera = CGSize(width: 1280, height: 720)
    private let render = CGSize(width: 1920, height: 1080)

    private func apply(_ transform: CGAffineTransform, to size: CGSize) -> CGRect {
        CGRect(origin: .zero, size: size).applying(transform)
    }

    func testFullFrameDestinationScalesTheSourceToFillIt() {
        let transform = PiPGeometry.transform(
            displaySize: camera,
            preferredTransform: .identity,
            destination: CGRect(origin: .zero, size: render)
        )
        let drawn = apply(transform, to: camera)

        XCTAssertEqual(drawn.width, 1920, accuracy: 0.001)
        XCTAssertEqual(drawn.height, 1080, accuracy: 0.001)
        XCTAssertEqual(drawn.minX, 0, accuracy: 0.001)
        XCTAssertEqual(drawn.minY, 0, accuracy: 0.001)
    }

    func testCornerDestinationPlacesTheSourceAtThatCorner() {
        // Bottom-right quarter-ish, matching the default overlay rect.
        let destination = CGRect(x: 1440, y: 810, width: 480, height: 270)
        let transform = PiPGeometry.transform(
            displaySize: camera,
            preferredTransform: .identity,
            destination: destination
        )
        let drawn = apply(transform, to: camera)

        XCTAssertEqual(drawn.minX, 1440, accuracy: 0.001)
        XCTAssertEqual(drawn.minY, 810, accuracy: 0.001)
        XCTAssertEqual(drawn.width, 480, accuracy: 0.001)
        XCTAssertEqual(drawn.height, 270, accuracy: 0.001)
    }

    func testAspectIsPreservedAndTheResultIsCenteredInATallerDestination() {
        // 16:9 source into a square destination: it fits by width and centres vertically,
        // rather than stretching.
        let destination = CGRect(x: 0, y: 0, width: 400, height: 400)
        let transform = PiPGeometry.transform(
            displaySize: camera,
            preferredTransform: .identity,
            destination: destination
        )
        let drawn = apply(transform, to: camera)

        XCTAssertEqual(drawn.width, 400, accuracy: 0.001)
        XCTAssertEqual(drawn.height, 225, accuracy: 0.001)
        XCTAssertEqual(drawn.minY, 87.5, accuracy: 0.001)
        XCTAssertEqual(drawn.width / drawn.height, camera.width / camera.height, accuracy: 0.001)
    }

    func testAspectIsPreservedAndCenteredInAWiderDestination() {
        let destination = CGRect(x: 0, y: 0, width: 800, height: 200)
        let transform = PiPGeometry.transform(
            displaySize: camera,
            preferredTransform: .identity,
            destination: destination
        )
        let drawn = apply(transform, to: camera)

        XCTAssertEqual(drawn.height, 200, accuracy: 0.001)
        XCTAssertEqual(drawn.width, 355.555, accuracy: 0.01)
        XCTAssertEqual(drawn.minX, 222.222, accuracy: 0.01)
    }

    func testMirroredSourceStillLandsInsideTheDestination() {
        // A Continuity Camera can carry a mirroring preferredTransform; applying it first
        // must not push the drawn frame outside the destination rect.
        let mirrored = CGAffineTransform(scaleX: -1, y: 1).translatedBy(x: -camera.width, y: 0)
        let destination = CGRect(x: 100, y: 50, width: 640, height: 360)

        let transform = PiPGeometry.transform(
            displaySize: camera,
            preferredTransform: mirrored,
            destination: destination
        )
        let drawn = apply(transform, to: camera).standardized

        XCTAssertEqual(drawn.minX, 100, accuracy: 0.001)
        XCTAssertEqual(drawn.minY, 50, accuracy: 0.001)
        XCTAssertEqual(drawn.width, 640, accuracy: 0.001)
        XCTAssertEqual(drawn.height, 360, accuracy: 0.001)
    }

    func testDegenerateInputsFallBackRatherThanProducingANaNTransform() {
        // A NaN or infinite value here would reach AVFoundation and raise an uncatchable
        // exception, so degenerate input must fall back instead of propagating.
        let cases: [(CGSize, CGRect)] = [
            (.zero, CGRect(x: 0, y: 0, width: 100, height: 100)),
            (camera, .zero),
            (camera, CGRect(x: 0, y: 0, width: 0, height: 100))
        ]

        for (displaySize, destination) in cases {
            let transform = PiPGeometry.transform(
                displaySize: displaySize,
                preferredTransform: .identity,
                destination: destination
            )
            XCTAssertTrue([transform.a, transform.b, transform.c, transform.d, transform.tx, transform.ty]
                .allSatisfy(\.isFinite))
        }
    }

    func testFittedRectMatchesWhereTheTransformActuallyDraws() {
        let destination = CGRect(x: 40, y: 60, width: 500, height: 500)
        let transform = PiPGeometry.transform(
            displaySize: camera,
            preferredTransform: .identity,
            destination: destination
        )

        let fitted = PiPGeometry.fittedRect(displaySize: camera, destination: destination)
        let drawn = apply(transform, to: camera)

        XCTAssertEqual(fitted.minX, drawn.minX, accuracy: 0.001)
        XCTAssertEqual(fitted.minY, drawn.minY, accuracy: 0.001)
        XCTAssertEqual(fitted.width, drawn.width, accuracy: 0.001)
        XCTAssertEqual(fitted.height, drawn.height, accuracy: 0.001)
    }

    // MARK: - Preview render size

    func testRenderSizeIsUnchangedWithoutALimit() {
        XCTAssertEqual(
            PiPGeometry.renderSize(render, maxDimension: nil),
            render
        )
    }

    func testRenderSizeIsUnchangedWhenAlreadyWithinTheLimit() {
        XCTAssertEqual(
            PiPGeometry.renderSize(CGSize(width: 640, height: 360), maxDimension: 1280),
            CGSize(width: 640, height: 360)
        )
    }

    func testRenderSizeScalesDownPreservingAspectAndStaysEven() {
        let scaled = PiPGeometry.renderSize(
            CGSize(width: 3024, height: 1964),
            maxDimension: 1280
        )

        XCTAssertEqual(scaled.width, 1280)
        XCTAssertEqual(Int(scaled.height) % 2, 0)
        XCTAssertEqual(scaled.height / scaled.width, 1964.0 / 3024.0, accuracy: 0.01)
    }
}
