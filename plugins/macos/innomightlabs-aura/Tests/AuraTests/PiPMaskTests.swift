import XCTest
import CoreImage
import AVFoundation
@testable import Aura

/// The camera overlay's shape, border, and shadow are drawn by Core Image rather than by
/// AVFoundation, so they are verified by rendering and reading pixels — the only way to know
/// a circle is actually round.
final class PiPMaskTests: XCTestCase {
    private let renderSize = CGSize(width: 400, height: 400)
    private let destination = CGRect(x: 100, y: 100, width: 200, height: 200)
    private let context = CIContext(options: [.useSoftwareRenderer: true])

    /// Solid green base, solid red overlay: any red pixel is overlay, any green pixel is base.
    private var base: CIImage {
        CIImage(color: CIColor(red: 0, green: 1, blue: 0))
            .cropped(to: CGRect(origin: .zero, size: renderSize))
    }

    private var overlay: CIImage {
        CIImage(color: CIColor(red: 1, green: 0, blue: 0))
            .cropped(to: CGRect(x: 0, y: 0, width: 200, height: 200))
    }

    /// Reads one pixel, in the top-left-origin space the edit model uses.
    private func pixel(_ image: CIImage, x: Int, y: Int) throws -> (r: UInt8, g: UInt8, b: UInt8) {
        let flippedY = Int(renderSize.height) - 1 - y
        var bytes = [UInt8](repeating: 0, count: 4)
        context.render(
            image,
            toBitmap: &bytes,
            rowBytes: 4,
            bounds: CGRect(x: x, y: flippedY, width: 1, height: 1),
            format: .RGBA8,
            colorSpace: CGColorSpaceCreateDeviceRGB()
        )
        return (bytes[0], bytes[1], bytes[2])
    }

    private func compose(_ style: PiPStyle, opacity: Double = 1) -> CIImage {
        PiPMask.compose(
            base: base,
            overlay: overlay,
            destination: destination,
            renderSize: renderSize,
            style: style,
            opacity: opacity
        )
    }

    // MARK: - Shape

    func testRectangleFillsItsWholeDestination() throws {
        let image = compose(.plain)

        // Every corner of the destination is overlay.
        for (x, y) in [(105, 105), (295, 105), (105, 295), (295, 295), (200, 200)] {
            let p = try pixel(image, x: x, y: y)
            XCTAssertGreaterThan(p.r, 200, "expected overlay at \(x),\(y)")
        }
    }

    func testCircleLeavesTheCornersShowingTheBaseLayer() throws {
        var style = PiPStyle.plain
        style.shape = .circle

        let image = compose(style)

        // Centre is overlay …
        let centre = try pixel(image, x: 200, y: 200)
        XCTAssertGreaterThan(centre.r, 200)
        XCTAssertLessThan(centre.g, 80)

        // … and the destination's corners are not, because a circle doesn't reach them.
        for (x, y) in [(104, 104), (296, 104), (104, 296), (296, 296)] {
            let corner = try pixel(image, x: x, y: y)
            XCTAssertGreaterThan(corner.g, 200, "expected base to show through at \(x),\(y)")
            XCTAssertLessThan(corner.r, 80, "expected no overlay at \(x),\(y)")
        }
    }

    func testCircleStillCoversTheMidpointsOfEachEdge() throws {
        var style = PiPStyle.plain
        style.shape = .circle

        let image = compose(style)

        // An inscribed circle touches each edge's midpoint.
        for (x, y) in [(200, 104), (200, 296), (104, 200), (296, 200)] {
            let p = try pixel(image, x: x, y: y)
            XCTAssertGreaterThan(p.r, 150, "expected overlay at edge midpoint \(x),\(y)")
        }
    }

    func testRoundedCutsTheCornersButLessThanACircle() throws {
        var rounded = PiPStyle.plain
        rounded.shape = .rounded
        rounded.cornerRadius = 0.15

        var circle = PiPStyle.plain
        circle.shape = .circle

        // Chosen deliberately: (115,115) is 120px from the centre so it falls outside the
        // inscribed circle (radius 100), but lies within the 30px corner arc of a 15%
        // rounded rect. Only a point that actually discriminates proves anything.
        let probe = (x: 115, y: 115)
        let roundedPixel = try pixel(compose(rounded), x: probe.x, y: probe.y)
        let circlePixel = try pixel(compose(circle), x: probe.x, y: probe.y)

        XCTAssertGreaterThan(roundedPixel.r, 150, "a 15% radius should keep this point")
        XCTAssertLessThan(circlePixel.r, 100, "a circle should clip this point")
    }

    func testZeroCornerRadiusIsIndistinguishableFromARectangle() throws {
        var style = PiPStyle.plain
        style.shape = .rounded
        style.cornerRadius = 0

        let corner = try pixel(compose(style), x: 105, y: 105)
        XCTAssertGreaterThan(corner.r, 200)
    }

    func testCircleIsSquaredOffSoItIsActuallyRound() {
        var style = PiPStyle.plain
        style.shape = .circle
        // A 16:9-ish overlay, which is what a camera's aspect ratio actually gives.
        let wide = CGRect(x: 100, y: 100, width: 256, height: 144)

        let drawn = PiPMask.drawnRect(for: style, in: wide)

        XCTAssertEqual(drawn.width, drawn.height, "a circle needs a square or it renders as a capsule")
        XCTAssertEqual(drawn.width, 144)
        XCTAssertEqual(drawn.midX, wide.midX, "and it should stay where the user put it")
        XCTAssertEqual(drawn.midY, wide.midY)
    }

    func testNonCircleShapesKeepTheirFullRect() {
        let wide = CGRect(x: 100, y: 100, width: 256, height: 144)

        XCTAssertEqual(PiPMask.drawnRect(for: .plain, in: wide), wide)

        var rounded = PiPStyle.plain
        rounded.shape = .rounded
        XCTAssertEqual(PiPMask.drawnRect(for: rounded, in: wide), wide)
    }

    func testCircleOnAWideOverlayLeavesTheSidesShowingTheBase() throws {
        var style = PiPStyle.plain
        style.shape = .circle

        // Destination 300 wide by 150 tall: a true circle occupies the middle 150px only.
        let wide = CGRect(x: 50, y: 125, width: 300, height: 150)
        let image = PiPMask.compose(
            base: base, overlay: overlay, destination: wide,
            renderSize: renderSize, style: style, opacity: 1
        )

        let middle = try pixel(image, x: 200, y: 200)
        XCTAssertGreaterThan(middle.r, 200, "the circle should cover the centre")

        // Well inside the requested rect horizontally, but outside a centred circle.
        let side = try pixel(image, x: 70, y: 200)
        XCTAssertGreaterThan(side.g, 200, "the base should show beside a circle on a wide rect")
        XCTAssertLessThan(side.r, 80)
    }

    // MARK: - Radius arithmetic

    func testCircleRadiusIsHalfTheShorterSide() {
        var style = PiPStyle.plain
        style.shape = .circle
        let wide = CGRect(x: 0, y: 0, width: 300, height: 100)

        XCTAssertEqual(PiPMask.cornerRadius(for: style, in: wide), 50)
    }

    func testRoundedRadiusIsAFractionOfTheShorterSideAndIsClamped() {
        var style = PiPStyle.plain
        style.shape = .rounded
        let rect = CGRect(x: 0, y: 0, width: 200, height: 100)

        style.cornerRadius = 0.25
        XCTAssertEqual(PiPMask.cornerRadius(for: style, in: rect), 25)

        // Beyond half the shorter side it would invert; clamped to a capsule instead.
        style.cornerRadius = 1.0
        XCTAssertEqual(PiPMask.cornerRadius(for: style, in: rect), 50)
    }

    func testRectangleHasNoRadius() {
        XCTAssertEqual(PiPMask.cornerRadius(for: .plain, in: destination), 0)
    }

    // MARK: - Border

    func testBorderDrawsAtTheEdgeAndNotThroughTheMiddle() throws {
        var style = PiPStyle.plain
        style.borderWidth = 0.05
        style.borderColor = [0, 0, 1] // blue, so it is distinguishable from both layers

        let image = compose(style)

        let edge = try pixel(image, x: 101, y: 200)
        XCTAssertGreaterThan(edge.b, 150, "expected the border at the edge")

        let middle = try pixel(image, x: 200, y: 200)
        XCTAssertGreaterThan(middle.r, 200, "the middle should still be overlay")
        XCTAssertLessThan(middle.b, 80)
    }

    func testBorderFollowsACircleRatherThanBoxingIt() throws {
        var style = PiPStyle.plain
        style.shape = .circle
        style.borderWidth = 0.05
        style.borderColor = [0, 0, 1]

        let image = compose(style)

        // On the circle's edge: border. In the square's corner: neither border nor overlay.
        let onCircle = try pixel(image, x: 200, y: 101)
        XCTAssertGreaterThan(onCircle.b, 120, "border should follow the curve")

        let corner = try pixel(image, x: 103, y: 103)
        XCTAssertLessThan(corner.b, 80, "border must not box a circle")
        XCTAssertGreaterThan(corner.g, 150, "base should still show at the corner")
    }

    // MARK: - Opacity and degenerate input

    func testHiddenOverlayLeavesTheBaseUntouched() throws {
        let image = compose(.plain, opacity: 0)

        let centre = try pixel(image, x: 200, y: 200)
        XCTAssertGreaterThan(centre.g, 200, "base should be unmodified")
        XCTAssertLessThan(centre.r, 80)
    }

    func testAnEmptyDestinationIsANoOp() {
        let image = PiPMask.compose(
            base: base, overlay: overlay, destination: .zero,
            renderSize: renderSize, style: .plain, opacity: 1
        )

        XCTAssertEqual(image.extent, base.extent)
    }

    func testOutputIsCroppedToTheRenderSize() {
        var style = PiPStyle.plain
        style.shadowOpacity = 0.6
        style.shadowRadius = 0.2

        // A shadow blurs outward; without cropping the image would grow past the frame and
        // the export would disagree with the preview.
        let image = compose(style)

        XCTAssertEqual(image.extent, CGRect(origin: .zero, size: renderSize))
    }

    // MARK: - Which compositor gets used

    func testPlainRectangleUsesTheCheapPath() {
        XCTAssertTrue(PiPStyle.plain.isPlainRectangle)
    }

    func testAnythingDecorativeNeedsTheCustomCompositor() {
        var circle = PiPStyle.plain
        circle.shape = .circle
        XCTAssertFalse(circle.isPlainRectangle)

        var bordered = PiPStyle.plain
        bordered.borderWidth = 0.02
        XCTAssertFalse(bordered.isPlainRectangle)

        var shadowed = PiPStyle.plain
        shadowed.shadowOpacity = 0.4
        XCTAssertFalse(shadowed.isPlainRectangle)
    }

    func testOutOfRangeStyleIsRejected() {
        var style = PiPStyle.plain
        style.cornerRadius = 5

        XCTAssertFalse(style.isValid)
        XCTAssertThrowsError(try SessionEdit.initial(duration: 10).applying(.setCameraStyle(style))) { error in
            XCTAssertEqual(error as? EditOperationError, .invalidCameraStyle)
        }
    }

    func testStyleRoundTripsThroughTheOperationAndTheDocument() throws {
        var style = PiPStyle.plain
        style.shape = .circle
        style.borderWidth = 0.03
        style.borderColor = [0.1, 0.2, 0.3]
        style.shadowOpacity = 0.5
        style.shadowRadius = 0.08

        let operation = EditOperation.setCameraStyle(style)
        let encoded = try JSONEncoder().encode(operation)
        XCTAssertEqual(try JSONDecoder().decode(EditOperation.self, from: encoded), operation)

        let document = try SessionEdit.initial(duration: 10).applying(operation)
        let reloaded = try JSONDecoder().decode(SessionEdit.self, from: try JSONEncoder().encode(document))
        XCTAssertEqual(reloaded.cameraStyle, style)
    }

    func testDocumentsWithoutAStyleDefaultToAPlainRectangle() throws {
        let json = """
        {"schemaVersion":1,"micTimeOffset":0,
         "clips":[{"id":"\(UUID().uuidString)","source":{"start":0,"end":30}}],
         "cameraOverlay":[{"t":0,"rect":{"x":0.7,"y":0.7,"width":0.25,"height":0.25},"visible":true}],
         "audioLanes":[]}
        """
        let decoded = try JSONDecoder().decode(SessionEdit.self, from: Data(json.utf8))

        XCTAssertEqual(decoded.cameraStyle, .plain)
    }
}
