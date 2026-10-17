import AVFoundation
import CoreImage
import XCTest
@testable import Aura

final class ScreenCropTests: XCTestCase {
    private let crop = NormalizedRect(x: 0.1, y: 0.2, width: 0.8, height: 0.6)

    private func viewport(rect: CGRect = CGRect(x: 200, y: 200, width: 1600, height: 600)) -> BrowserViewportMetadata {
        BrowserViewportMetadata(viewportRect: rect,
                                viewport: .init(width: 800, height: 300, devicePixelRatio: 2),
                                frameSize: CGSize(width: 2000, height: 1000), pixelsPerCSSPixel: 2)
    }

    private func probe(_ kind: TrackKind) -> SourceTrackProbe {
        SourceTrackProbe(url: URL(fileURLWithPath: "/screen-crop-test.mov"), kind: kind,
                         duration: Timeline.time(seconds: 10),
                         displaySize: CGSize(width: 2000, height: 1000), preferredTransform: .identity)
    }

    func testFlatOperationRoundTripsIncludingExplicitNull() throws {
        for operation in [EditOperation.setScreenCrop(crop), .setScreenCrop(nil)] {
            let data = try JSONEncoder().encode(operation)
            let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            XCTAssertEqual(Set(json.keys), ["op", "rect"])
            XCTAssertEqual(json["op"] as? String, "set_screen_crop")
            if operation == .setScreenCrop(nil) { XCTAssertTrue(json["rect"] is NSNull) }
            XCTAssertEqual(try JSONDecoder().decode(EditOperation.self, from: data), operation)
        }
        XCTAssertThrowsError(try JSONDecoder().decode(EditOperation.self, from: Data(#"{"op":"set_screen_crop"}"#.utf8)))
    }

    func testCropValidationAndClearingDoNotTouchOtherEdits() throws {
        let original = try SessionEdit.initial(duration: 10)
            .applying(.removeRange(TimeSpan(start: 2, end: 3)))
            .applying(.rename("Demo"))
        let cropped = try original.applying(.setScreenCrop(crop))
        XCTAssertEqual(cropped.screenCrop, crop)
        XCTAssertEqual(try cropped.applying(.setScreenCrop(nil)), original)
        let invalid = [
            NormalizedRect(x: -0.01, y: 0, width: 1, height: 1),
            NormalizedRect(x: 0, y: 0.5, width: 1, height: 0.6),
            NormalizedRect(x: 0.5, y: 0, width: 0.6, height: 1),
            NormalizedRect(x: 0, y: 0, width: 0, height: 1),
            NormalizedRect(x: 0, y: 0, width: 1, height: -1),
            NormalizedRect(x: .nan, y: 0, width: 1, height: 1),
            NormalizedRect(x: 0, y: .infinity, width: 1, height: 1)
        ]
        for rect in invalid {
            XCTAssertThrowsError(try cropped.applying(.setScreenCrop(rect))) {
                XCTAssertEqual($0 as? EditOperationError, .invalidRect)
            }
        }
        XCTAssertNoThrow(try original.applying(.setScreenCrop(.init(x: 0, y: 0, width: 1, height: 1))))
    }

    func testV2MigrationPreservesTimelineAndSpeechAndDefaultsToNoCrop() throws {
        var old = try SessionEdit.initial(duration: 10)
            .applying(.removeRange(TimeSpan(start: 2, end: 3)))
            .applying(.splitClip(at: 5))
            .applying(.rename("Existing work"))
        old.speechReplacements = [SpeechReplacement(span: TimeSpan(start: 6, end: 7),
                                                    text: "new", originalText: "old", duration: 1.2)]
        old.schemaVersion = 2
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(old)) as? [String: Any])
        json.removeValue(forKey: "screenCrop")
        json.removeValue(forKey: "hasSeededBrowserViewport")
        let data = try JSONSerialization.data(withJSONObject: json)
        guard case .migrated(let migrated) = SessionEditMigration.decode(data, recordingDuration: 99) else {
            return XCTFail("Expected v2 migration")
        }
        old.schemaVersion = SessionEdit.currentSchemaVersion
        XCTAssertEqual(migrated, old)
        XCTAssertNil(migrated.screenCrop)
        XCTAssertFalse(migrated.hasSeededBrowserViewport)
        guard case .current(let reopened) = SessionEditMigration.decode(try JSONEncoder().encode(migrated), recordingDuration: 99) else {
            return XCTFail("Expected current schema after saving")
        }
        XCTAssertEqual(reopened, migrated)
        json.removeValue(forKey: "cuts")
        XCTAssertEqual(SessionEditMigration.decode(try JSONSerialization.data(withJSONObject: json), recordingDuration: 10), .unreadable)
    }

    func testViewportConversionUsesSourcePixelsNotCSSMetrics() {
        XCTAssertEqual(BrowserViewportCropSeed.operation(viewport: viewport()), .setScreenCrop(crop))
        for rect in [CGRect.zero, CGRect(x: -1, y: 200, width: 1600, height: 600),
                     CGRect(x: 200, y: 200, width: 2000, height: 600)] {
            XCTAssertNil(BrowserViewportCropSeed.operation(viewport: viewport(rect: rect)))
        }
    }

    func testResolverCropsScreenSizeButNeverPromotedCamera() throws {
        let document = try SessionEdit.initial(duration: 10).applying(.setScreenCrop(crop))
        let screen = TimelineResolver.resolve(document: document, probes: [probe(.screen), probe(.camera)])
        XCTAssertEqual(screen.renderSize, CGSize(width: 1600, height: 600))
        XCTAssertEqual(screen.screenCrop, crop)
        XCTAssertFalse(screen.canUseLayerInstructions)
        let camera = TimelineResolver.resolve(document: document, probes: [probe(.camera)])
        XCTAssertEqual(camera.renderSize, CGSize(width: 2000, height: 1000))
        XCTAssertNil(camera.screenCrop)
        XCTAssertEqual(screen.timeMap, camera.timeMap)
        let clear = TimelineResolver.resolve(document: try document.applying(.setScreenCrop(nil)), probes: [probe(.screen)])
        XCTAssertEqual(clear.renderSize, CGSize(width: 2000, height: 1000))
        XCTAssertTrue(clear.canUseLayerInstructions)
    }

    func testCoreImageCropsTopLeftSourceRectAtPreviewAndExportSizes() throws {
        // Red toolbar above a green viewport and blue content below it: flipping y incorrectly
        // exposes blue. An asymmetric crop makes that error visible at either output size.
        let bounds = CGRect(x: 0, y: 0, width: 100, height: 100)
        let source = CIImage(color: CIColor(red: 1, green: 0, blue: 0)).cropped(to: bounds)
        let viewport = CIImage(color: CIColor(red: 0, green: 1, blue: 0))
            .cropped(to: CGRect(x: 10, y: 50, width: 80, height: 30))
        let bottom = CIImage(color: CIColor(red: 0, green: 0, blue: 1))
            .cropped(to: CGRect(x: 0, y: 0, width: 100, height: 50))
        let image = viewport.composited(over: bottom.composited(over: source))
        let crop = NormalizedRect(x: 0.1, y: 0.2, width: 0.8, height: 0.3)
        let context = CIContext(options: [.useSoftwareRenderer: true])
        for size in [CGSize(width: 80, height: 30), CGSize(width: 40, height: 16)] {
            let result = CoreImagePiPCompositor.screenImage(image, crop: crop, renderSize: size)
            var pixel = [UInt8](repeating: 0, count: 4)
            context.render(result, toBitmap: &pixel, rowBytes: 4,
                           bounds: CGRect(x: size.width / 2, y: size.height / 2, width: 1, height: 1),
                           format: .RGBA8, colorSpace: CGColorSpaceCreateDeviceRGB())
            XCTAssertEqual(pixel, [0, 255, 0, 255])
            XCTAssertEqual(result.extent.midX, size.width / 2, accuracy: 0.001)
            XCTAssertEqual(result.extent.midY, size.height / 2, accuracy: 0.001)
        }
    }

    @MainActor
    func testPreviewAndExportCarryTheSameCropWithoutRewritingSource() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let url = root.appendingPathComponent("screen.mov")
        try await TestMedia.writeVideo(to: url, seconds: 1)
        let originalBytes = try Data(contentsOf: url)
        let probed = await SourceTrackProbe.probe(url: url, kind: .screen)
                let source = try XCTUnwrap(probed)
        let document = try SessionEdit.initial(duration: 1).applying(.setScreenCrop(crop))
        let timeline = TimelineResolver.resolve(document: document, probes: [source])
        let builder = LayerInstructionCompositionBuilder()
        for limit: CGFloat? in [nil, 64] {
            let built = try await builder.build(timeline, maxRenderDimension: limit)
            let composition = try XCTUnwrap(built.videoComposition)
            XCTAssertTrue(composition.customVideoCompositorClass == CoreImagePiPCompositor.self)
            XCTAssertFalse(composition.instructions.isEmpty)
            for instruction in composition.instructions {
                let cropInstruction = try XCTUnwrap(instruction as? PiPCompositionInstruction)
                XCTAssertEqual(cropInstruction.screenCrop, crop)
                XCTAssertEqual(cropInstruction.renderSize, built.renderSize)
            }
            if let limit { XCTAssertLessThanOrEqual(max(built.renderSize.width, built.renderSize.height), limit) }
        }
        XCTAssertEqual(try Data(contentsOf: url), originalBytes)
        XCTAssertEqual(document.screenCrop, crop)
    }

    func testDigestIncludesCurrentSourceFrameCrop() throws {
        let document = try SessionEdit.initial(duration: 10).applying(.setScreenCrop(crop))
        let digest = SessionDigest.make(sessionID: "crop", duration: 10, probes: [probe(.screen)],
                                        events: EventTimeline(events: []), document: document, transcript: nil)
        XCTAssertEqual(digest.screenCrop, crop)
    }

    @MainActor
    func testSeedIsOneUndoableEditAndDoesNotReturnAfterReopen() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let folder = SessionFolder.load(rootURL: root)
        let url = root.appendingPathComponent("viewport.json")
        try JSONEncoder().encode(viewport()).write(to: url)
        let store = EditDocumentStore.load(folder: folder, duration: 10, micTimeOffset: 0)
        store.seedBrowserViewport(from: url)
        XCTAssertEqual(store.document.screenCrop, crop)
        XCTAssertTrue(store.canUndo)
        store.seedBrowserViewport(from: url)
        store.undo()
        XCTAssertNil(store.document.screenCrop)
        XCTAssertTrue(store.document.hasSeededBrowserViewport)
        XCTAssertFalse(store.canUndo)
        store.redo()
        XCTAssertEqual(store.document.screenCrop, crop)
        store.undo()
        store.flush()
        let reopened = EditDocumentStore.load(folder: folder, duration: 10, micTimeOffset: 0)
        reopened.seedBrowserViewport(from: url)
        XCTAssertNil(reopened.document.screenCrop)
        XCTAssertFalse(reopened.canUndo)
        reopened.flush()
    }

    @MainActor
    func testMissingOrInvalidViewportDoesNotEditAndExistingCropIsPreserved() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let url = root.appendingPathComponent("viewport.json")
        let original = try SessionEdit.initial(duration: 10).applying(.setScreenCrop(.defaultCameraOverlay))
        let store = EditDocumentStore(document: original, fileURL: root.appendingPathComponent("edit.json"))
        store.seedBrowserViewport(from: url)
        XCTAssertEqual(store.document, original)
        try Data("not json".utf8).write(to: url)
        store.seedBrowserViewport(from: url)
        XCTAssertEqual(store.document, original)
        try JSONEncoder().encode(viewport()).write(to: url)
        store.seedBrowserViewport(from: url)
        XCTAssertEqual(store.document.screenCrop, original.screenCrop)
        XCTAssertTrue(store.document.hasSeededBrowserViewport)
        XCTAssertFalse(store.canUndo)
        store.flush()
    }
}
