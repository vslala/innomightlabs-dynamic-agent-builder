import AVFoundation
import XCTest
@testable import Aura

/// Real frames through the real compositor: the pieces are tested alone elsewhere, and this proves
/// they agree once AVFoundation hands the compositor a time and asks for a picture.
@MainActor
final class DemoRenderingTests: XCTestCase {
    private var root: URL!
    private var folder: SessionFolder!
    private let size = CGSize(width: 640, height: 360)

    override func setUp() async throws {
        root = FileManager.default.temporaryDirectory.appendingPathComponent("aura-demo-render-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        folder = SessionFolder.load(rootURL: root)
        try await TestMedia.writeVideo(to: folder.screenURL, seconds: 4, size: size, grey: 128)
        try Data(#"{"ts":0,"type":"record_start","media_ts":0}"#.utf8).write(to: folder.eventsURL)
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: root)
    }

    /// The pointer sits at (400, 180) from 0.5s, clicks at 3.0s. CSS pixels are source pixels.
    private var path: CursorPath {
        CursorPath(log: ActionLog(entries: [
            .init(t: 0.5, stepID: "a", kind: .mouseMove, point: CGPoint(x: 400, y: 180)),
            .init(t: 3.0, stepID: "a", kind: .mouseDown, point: CGPoint(x: 400, y: 180))
        ]), viewport: BrowserViewportMetadata(
            viewportRect: CGRect(origin: .zero, size: size), viewport: .init(width: 640, height: 360, devicePixelRatio: 1),
            frameSize: size, pixelsPerCSSPixel: 1))
    }

    private func frame(of document: SessionEdit, at seconds: Double) async throws -> (pixels: [UInt8], width: Int, height: Int) {
        let probes = await SourceTrackProbe.probeAll(in: folder)
        let timeline = TimelineResolver.resolve(document: document, probes: probes, cursorPath: path)
        let built = try await LayerInstructionCompositionBuilder().build(timeline)
        let generator = AVAssetImageGenerator(asset: built.asset)
        generator.videoComposition = built.videoComposition
        generator.requestedTimeToleranceBefore = .zero
        generator.requestedTimeToleranceAfter = .zero
        // `copyCGImage` rather than the async `image(at:)`: the generator is not Sendable, and this is a test.
        let image = try generator.copyCGImage(at: CMTime(seconds: seconds, preferredTimescale: 600), actualTime: nil)

        let width = image.width, height = image.height
        var pixels = [UInt8](repeating: 0, count: width * height * 4)
        let context = CGContext(data: &pixels, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
                                space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        if ProcessInfo.processInfo.environment["AURA_DUMP_FRAMES"] != nil {
            let url = URL(fileURLWithPath: "/tmp/aura-demo-frame-\(String(format: "%.2f", seconds)).png")
            if let destination = CGImageDestinationCreateWithURL(url as CFURL, "public.png" as CFString, 1, nil) {
                CGImageDestinationAddImage(destination, image, nil)
                CGImageDestinationFinalize(destination)
            }
        }
        return (pixels, width, height)
    }

    /// Bounding box, top-left origin, of pixels the cursor's dark fill or white outline could be:
    /// anything that is not the flat grey (128) behind it.
    private func drawn(_ frame: (pixels: [UInt8], width: Int, height: Int), where match: (UInt8, UInt8, UInt8) -> Bool) -> CGRect? {
        var minX = Int.max, minY = Int.max, maxX = -1, maxY = -1
        for y in 0..<frame.height {
            for x in 0..<frame.width {
                let i = (y * frame.width + x) * 4
                if match(frame.pixels[i], frame.pixels[i + 1], frame.pixels[i + 2]) {
                    minX = min(minX, x); maxX = max(maxX, x); minY = min(minY, y); maxY = max(maxY, y)
                }
            }
        }
        return maxX < 0 ? nil : CGRect(x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1)
    }

    private func notGrey(_ r: UInt8, _ g: UInt8, _ b: UInt8) -> Bool {
        abs(Int(r) - 128) > 40 || abs(Int(g) - 128) > 40 || abs(Int(b) - 128) > 40
    }

    func testTheCursorAppearsOnlyOnceThePointerHasMovedAndSitsWhereThePageHadIt() async throws {
        let document = SessionEdit.initial(duration: 4)
        let before = try await frame(of: document, at: 0.25)
        XCTAssertNil(drawn(before, where: notGrey), "no pointer event yet, so nothing is drawn")

        let during = try await frame(of: document, at: 1.5)
        let box = try XCTUnwrap(drawn(during, where: notGrey), "the cursor is drawn")
        XCTAssertEqual(box.minX, 400, accuracy: 6, "its tip is on the pointer's x")
        XCTAssertEqual(box.minY, 180, accuracy: 6, "and y, top-left origin")
        XCTAssertLessThan(box.width, 40)
        XCTAssertLessThan(box.height, 60)
    }

    func testAClickDrawsARippleThatSpreadsAndThenIsGone() async throws {
        let document = SessionEdit.initial(duration: 4)
        func blueish(_ r: UInt8, _ g: UInt8, _ b: UInt8) -> Bool { Int(b) - Int(r) > 40 }
        let early = try await frame(of: document, at: 3.1)
        let late = try await frame(of: document, at: 3.4)
        let first = try XCTUnwrap(drawn(early, where: blueish), "a ripple starts at the click")
        let second = try XCTUnwrap(drawn(late, where: blueish))
        XCTAssertGreaterThan(second.width, first.width, "and spreads")
        XCTAssertEqual(first.midX, 400, accuracy: 6)
        XCTAssertEqual(first.midY, 180, accuracy: 6)
        let after = try await frame(of: document, at: 3.8)
        XCTAssertNil(drawn(after, where: blueish), "and is gone after half a second")

        var quiet = document
        quiet = try quiet.applying(.setCursorStyle(CursorStyle(visible: true, scale: 1, ripple: false)))
        let without = try await frame(of: quiet, at: 3.1)
        XCTAssertNil(drawn(without, where: blueish), "ripples can be turned off")
    }

    func testZoomMovesThePicture_AndTheCursorMovesWithIt() async throws {
        // The right half, vertically centred: the pointer at source (400, 180) lands a quarter of the
        // way across the zoomed picture and halfway down it.
        let zoom = ZoomSegment(span: TimeSpan(start: 1, end: 3), rect: NormalizedRect(x: 0.5, y: 0.25, width: 0.5, height: 0.5), easeSeconds: 0.5)
        let document = try SessionEdit.initial(duration: 4).applying(.setZoom(zoom))

        let unzoomed = try await frame(of: document, at: 0.75)
        let boxBefore = try XCTUnwrap(drawn(unzoomed, where: notGrey))
        XCTAssertEqual(boxBefore.minX, 400, accuracy: 6)

        let zoomed = try await frame(of: document, at: 2.0)
        let box = try XCTUnwrap(drawn(zoomed, where: notGrey))
        XCTAssertEqual(box.minX, 640 * 0.25, accuracy: 8, "the cursor went through the same zoom as the picture")
        XCTAssertEqual(box.minY, 360 * 0.5, accuracy: 8)
        XCTAssertGreaterThan(box.height, boxBefore.height * 0.8, "while staying cursor-sized on screen")
        XCTAssertLessThan(box.height, boxBefore.height * 1.3)

        let after = try await frame(of: document, at: 3.5)
        let boxAfter = try XCTUnwrap(drawn(after, where: notGrey))
        XCTAssertEqual(boxAfter.minX, 400, accuracy: 6, "back to the full frame once the zoom has eased out")
    }

    func testACutBeforeTheCursorMovesItsTimeButNotItsPlace() async throws {
        // Remove 0–1s: the pointer was already there at 0.5s, so at playhead 0.5s (source 1.5s) it is
        // where it was, not shifted by the cut.
        let document = try SessionEdit.initial(duration: 4).applying(.removeRange(TimeSpan(start: 0, end: 1)))
        let result = try await frame(of: document, at: 0.5)
        let box = try XCTUnwrap(drawn(result, where: notGrey))
        XCTAssertEqual(box.minX, 400, accuracy: 6)
    }
}
