import AVFoundation
import CoreImage
import XCTest
@testable import Aura

final class DemoEffectsTests: XCTestCase {
    private let bigZoom = NormalizedRect(x: 0.5, y: 0.5, width: 0.5, height: 0.5)

    private func zoom(_ start: TimeInterval, _ end: TimeInterval, rect: NormalizedRect? = nil,
                      ease: TimeInterval = 0.5, id: UUID = UUID()) -> ZoomSegment {
        ZoomSegment(id: id, span: TimeSpan(start: start, end: end), rect: rect ?? bigZoom, easeSeconds: ease)
    }

    // MARK: - ZoomTrack

    func testZoomIsFullFrameOutsideAndHeldInsideTheSpan() {
        let segments = [zoom(2, 6)]
        XCTAssertEqual(ZoomTrack.rect(at: 1, in: segments), SessionEdit.fullFrame)
        XCTAssertEqual(ZoomTrack.rect(at: 6, in: segments), SessionEdit.fullFrame, "the span is half-open")
        XCTAssertEqual(ZoomTrack.rect(at: 4, in: segments), bigZoom)
        XCTAssertEqual(ZoomTrack.rect(at: 2, in: segments), SessionEdit.fullFrame, "eases in from the full frame")
    }

    func testZoomEasesSmoothlyIn() {
        let segments = [zoom(2, 6, ease: 1)]
        let halfway = ZoomTrack.rect(at: 2.5, in: segments)
        XCTAssertEqual(halfway.width, 0.75, accuracy: 1e-9, "smoothstep is 0.5 at the midpoint")
        var last = 1.0
        for step in 1...10 {
            let width = ZoomTrack.rect(at: 2 + Double(step) / 10, in: segments).width
            XCTAssertLessThanOrEqual(width, last + 1e-9, "never steps back out while easing in")
            last = width
        }
        XCTAssertEqual(ZoomTrack.rect(at: 5.5, in: segments).width, 0.75, accuracy: 1e-9, "and eases out the same way")
    }

    func testAShortSpanNeverLetsTheRiseAndFallOverlap() {
        let segment = zoom(0, 1, ease: 1.5)
        XCTAssertEqual(ZoomTrack.factor(of: segment, at: 0.5), 1, accuracy: 1e-9)
        XCTAssertLessThanOrEqual(ZoomTrack.factor(of: segment, at: 0.25), 1)
    }

    func testOverlappingZoomsTakeTheStrongerNeverTheSum() {
        let other = NormalizedRect(x: 0, y: 0, width: 0.4, height: 0.4)
        let segments = [zoom(0, 10, rect: bigZoom), zoom(4, 8, rect: other)]
        let rect = ZoomTrack.rect(at: 6, in: segments)
        XCTAssertTrue(rect.isValidScreenCrop)
        XCTAssertTrue([bigZoom, other].contains(rect))
    }

    // MARK: - Zoom validity

    func testZoomValidity() {
        XCTAssertTrue(zoom(1, 3).isValid)
        XCTAssertFalse(zoom(1, 1.2).isValid, "shorter than two eases is a wobble")
        XCTAssertFalse(zoom(1, 3, rect: NormalizedRect(x: 0, y: 0, width: 0.2, height: 0.2)).isValid, "past 4x")
        XCTAssertFalse(zoom(1, 3, rect: NormalizedRect(x: 0.6, y: 0, width: 0.6, height: 0.5)).isValid, "outside the frame")
        XCTAssertFalse(zoom(1, 3, ease: 5).isValid)
        XCTAssertFalse(zoom(.nan, 3).isValid)
    }

    // MARK: - Operations

    private func edit(_ seconds: TimeInterval = 20) -> SessionEdit { SessionEdit.initial(duration: seconds) }

    func testSetZoomUpsertsByIdAndKeepsStartOrder() throws {
        let id = UUID()
        var document = try edit().applying(.setZoom(zoom(8, 10)))
        document = try document.applying(.setZoom(zoom(2, 4, id: id)))
        XCTAssertEqual(document.zooms.map(\.span.start), [2, 8])
        document = try document.applying(.setZoom(zoom(3, 5, id: id)))
        XCTAssertEqual(document.zooms.map(\.span.start), [3, 8], "same id replaces rather than adding")
    }

    func testInvalidZoomsAreRejectedNotClamped() throws {
        let document = try edit(10).applying(.setZoom(zoom(1, 3)))
        for bad in [zoom(1, 1.1), zoom(9, 12), zoom(1, 3, rect: NormalizedRect(x: 0, y: 0, width: 0.1, height: 0.1))] {
            XCTAssertThrowsError(try document.applying(.setZoom(bad))) {
                XCTAssertEqual($0 as? EditOperationError, .invalidZoom)
            }
        }
    }

    func testRemoveZoomsAndUnknownIds() throws {
        let one = zoom(1, 3), two = zoom(5, 7)
        var document = try edit().applying(.setZoom(one)).applying(.setZoom(two))
        document = try document.applying(.removeZooms(ids: [one.id]))
        XCTAssertEqual(document.zooms.map(\.id), [two.id])
        XCTAssertThrowsError(try document.applying(.removeZooms(ids: [UUID()]))) {
            XCTAssertEqual($0 as? EditOperationError, .noSuchZoom)
        }
    }

    func testCursorStyleIsValidated() throws {
        let document = try edit().applying(.setCursorStyle(CursorStyle(visible: true, scale: 2, ripple: false)))
        XCTAssertEqual(document.cursorStyle, CursorStyle(visible: true, scale: 2, ripple: false))
        for scale in [0.1, 4, .nan] {
            XCTAssertThrowsError(try document.applying(.setCursorStyle(CursorStyle(scale: scale)))) {
                XCTAssertEqual($0 as? EditOperationError, .invalidCursorStyle)
            }
        }
    }

    func testNarrationNeedsAClipAndNeverOverlapsAnotherLine() throws {
        let draft = NarrationLine(at: 1, text: "Open the builder")
        XCTAssertThrowsError(try edit().applying(.setNarration(draft))) {
            XCTAssertEqual($0 as? EditOperationError, .narrationNotRendered)
        }
        var line = draft
        line.duration = 3
        var document = try edit().applying(.setNarration(line))
        XCTAssertEqual(document.narration, [line])

        var overlapping = NarrationLine(at: 3, text: "Too soon", duration: 2)
        XCTAssertThrowsError(try document.applying(.setNarration(overlapping))) {
            XCTAssertEqual($0 as? EditOperationError, .narrationOverlaps)
        }
        overlapping.at = 4
        document = try document.applying(.setNarration(overlapping))
        XCTAssertEqual(document.narration.map(\.at), [1, 4])

        var rewritten = line
        rewritten.text = "A different sentence"
        rewritten.duration = 2.5
        document = try document.applying(.setNarration(rewritten))
        XCTAssertEqual(document.narration.count, 2, "the same id replaces, so a rewrite does not overlap its old self")
        XCTAssertThrowsError(try document.applying(.setNarration(NarrationLine(at: 9, text: "  ", duration: 1)))) {
            XCTAssertEqual($0 as? EditOperationError, .emptyNarrationText)
        }
    }

    func testRemoveNarration() throws {
        let line = NarrationLine(at: 1, text: "Hello", duration: 2)
        let document = try edit().applying(.setNarration(line)).applying(.removeNarration(ids: [line.id]))
        XCTAssertTrue(document.narration.isEmpty)
        XCTAssertThrowsError(try document.applying(.removeNarration(ids: [line.id]))) {
            XCTAssertEqual($0 as? EditOperationError, .noSuchNarration)
        }
    }

    // MARK: - Wire format

    func testOperationsRoundTripAsFlatJSON() throws {
        let line = NarrationLine(at: 1.5, text: "Hello", duration: 2)
        let operations: [(EditOperation, Set<String>)] = [
            (.setZoom(zoom(1, 3)), ["op", "id", "start", "end", "rect", "ease"]),
            (.removeZooms(ids: [UUID()]), ["op", "ids"]),
            (.setCursorStyle(CursorStyle(visible: false, scale: 2, ripple: false)), ["op", "visible", "scale", "ripple"]),
            (.setNarration(line), ["op", "id", "t", "text", "duration"]),
            (.removeNarration(ids: [UUID()]), ["op", "ids"])
        ]
        for (operation, keys) in operations {
            let data = try JSONEncoder().encode(operation)
            let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            XCTAssertEqual(Set(json.keys), keys)
            XCTAssertEqual(try JSONDecoder().decode(EditOperation.self, from: data), operation)
        }
    }

    func testAnAgentCanProposeTheMinimalShapes() throws {
        let zoomJSON = #"{"op":"set_zoom","start":4,"end":7,"rect":{"x":0.5,"y":0.1,"width":0.5,"height":0.5}}"#
        guard case .setZoom(let zoom) = try JSONDecoder().decode(EditOperation.self, from: Data(zoomJSON.utf8)) else {
            return XCTFail("set_zoom did not decode")
        }
        XCTAssertEqual(zoom.span, TimeSpan(start: 4, end: 7))
        XCTAssertEqual(zoom.easeSeconds, ZoomSegment.defaultEase)

        guard case .setNarration(let line) = try JSONDecoder().decode(
            EditOperation.self, from: Data(#"{"op":"set_narration","t":3,"text":"Click Save."}"#.utf8)
        ) else { return XCTFail("set_narration did not decode") }
        XCTAssertTrue(line.isDraft, "an agent's rewrite is a draft until it has been spoken")
        XCTAssertEqual(line.at, 3)

        // `at` is accepted for the time, as a model reaches for it.
        XCTAssertNoThrow(try JSONDecoder().decode(EditOperation.self, from: Data(#"{"op":"set_narration","at":3,"text":"x"}"#.utf8)))
        guard case .setCursorStyle(let style) = try JSONDecoder().decode(
            EditOperation.self, from: Data(#"{"op":"set_cursor_style","scale":1.5}"#.utf8)
        ) else { return XCTFail("set_cursor_style did not decode") }
        XCTAssertEqual(style, CursorStyle(visible: true, scale: 1.5, ripple: true))
    }

    func testV3DocumentsMigrateWithoutLosingEditsAndGainEmptyEffects() throws {
        var old = try edit(10).applying(.removeRange(TimeSpan(start: 2, end: 3))).applying(.rename("Kept"))
        old.schemaVersion = 3
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(old)) as? [String: Any])
        for key in ["zooms", "cursorStyle", "narration", "hasSeededDemoEffects"] { json.removeValue(forKey: key) }
        guard case .migrated(let migrated) = SessionEditMigration.decode(
            try JSONSerialization.data(withJSONObject: json), recordingDuration: 99
        ) else { return XCTFail("Expected v3 migration") }
        XCTAssertEqual(migrated.schemaVersion, SessionEdit.currentSchemaVersion)
        XCTAssertEqual(migrated.cuts, old.cuts)
        XCTAssertEqual(migrated.name, "Kept")
        XCTAssertTrue(migrated.zooms.isEmpty)
        XCTAssertTrue(migrated.narration.isEmpty)
        XCTAssertEqual(migrated.cursorStyle, .standard)
        XCTAssertFalse(migrated.hasSeededDemoEffects)
    }

    // MARK: - CursorPath

    private let viewport = BrowserViewportMetadata(
        viewportRect: CGRect(x: 200, y: 200, width: 1600, height: 600),
        viewport: .init(width: 800, height: 300, devicePixelRatio: 2),
        frameSize: CGSize(width: 2000, height: 1000), pixelsPerCSSPixel: 2)

    func testCursorMapsCSSPixelsToSourceFractionsAndInterpolates() throws {
        let log = ActionLog(entries: [
            .init(t: 1, stepID: "a", kind: .mouseMove, point: CGPoint(x: 0, y: 0)),
            .init(t: 2, stepID: "a", kind: .mouseMove, point: CGPoint(x: 800, y: 300))
        ])
        let path = CursorPath(log: log, viewport: viewport)
        XCTAssertNil(path.position(at: 0.5), "no cursor before the first pointer event")
        XCTAssertEqual(try XCTUnwrap(path.position(at: 1)), CGPoint(x: 0.1, y: 0.2))
        XCTAssertEqual(try XCTUnwrap(path.position(at: 2)), CGPoint(x: 0.9, y: 0.8))
        let mid = try XCTUnwrap(path.position(at: 1.5))
        XCTAssertEqual(mid.x, 0.5, accuracy: 1e-9)
        XCTAssertEqual(mid.y, 0.5, accuracy: 1e-9)
        XCTAssertEqual(try XCTUnwrap(path.position(at: 99)), CGPoint(x: 0.9, y: 0.8), "rests where it last was")
    }

    func testClicksMakeRipplesThatFinish() {
        let log = ActionLog(entries: [
            .init(t: 3, stepID: "a", kind: .mouseDown, point: CGPoint(x: 400, y: 150)),
            .init(t: 3.05, stepID: "a", kind: .mouseUp, point: CGPoint(x: 400, y: 150))
        ])
        let path = CursorPath(log: log, viewport: viewport)
        XCTAssertTrue(path.ripples(at: 2.9).isEmpty)
        let early = path.ripples(at: 3.1)
        XCTAssertEqual(early.count, 1)
        XCTAssertEqual(early[0].progress, 0.1 / CursorPath.rippleDuration, accuracy: 1e-9)
        XCTAssertEqual(early[0].position, CGPoint(x: 0.5, y: 0.5))
        XCTAssertTrue(path.ripples(at: 3.6).isEmpty)
        XCTAssertNotNil(path.position(at: 3), "a click also places the pointer")
    }

    func testOnlyTheStepsThatAskForARippleMakeOne() {
        let log = ActionLog(entries: [
            .init(t: 1, stepID: "big", kind: .mouseDown, point: CGPoint(x: 100, y: 100)),
            .init(t: 2, stepID: "small", kind: .mouseDown, point: CGPoint(x: 200, y: 100))
        ])
        let selective = CursorPath(log: log, viewport: viewport, rippleSteps: ["big"])
        XCTAssertEqual(selective.ripples(at: 1.1).count, 1)
        XCTAssertTrue(selective.ripples(at: 2.1).isEmpty, "this click did not ask for one")
        XCTAssertNotNil(selective.position(at: 2.1), "but the pointer still goes there")
        XCTAssertEqual(CursorPath(log: log, viewport: viewport).ripples(at: 2.1).count, 1, "an unknown spec ripples every click")
        XCTAssertTrue(CursorPath(log: log, viewport: viewport, rippleSteps: []).ripples(at: 1.1).isEmpty)
    }

    func testAnEmptyLogMakesAnEmptyPath() {
        XCTAssertTrue(CursorPath(log: ActionLog(entries: []), viewport: viewport).isEmpty)
    }

    // MARK: - DemoEditSeed

    func testTargetRegionFramesTheElementAtTheTargetMagnification() throws {
        let visible = CGRect(x: 200, y: 200, width: 1600, height: 600)
        // A mid-size element is framed at 2.5x its own size.
        let mid = try XCTUnwrap(DemoEditSeed.targetRegion(for: CGRect(x: 400, y: 300, width: 200, height: 80), in: visible))
        XCTAssertEqual(mid.width, mid.height, accuracy: 1e-9, "same aspect as the frame is square when normalized")
        XCTAssertEqual(mid.width, (80.0 / 600) * DemoEditSeed.targetMagnification, accuracy: 1e-9)
        XCTAssertTrue(mid.isValidScreenCrop)
        // A tiny one stops at the magnification cap, and a corner element is kept inside the frame.
        let region = try XCTUnwrap(DemoEditSeed.targetRegion(for: CGRect(x: 210, y: 210, width: 100, height: 40), in: visible))
        XCTAssertEqual(region.width, 1 / ZoomSegment.maximumMagnification, accuracy: 1e-9)
        XCTAssertEqual(region.x, 0, accuracy: 1e-9)
        XCTAssertEqual(region.y, 0, accuracy: 1e-9)
        XCTAssertTrue(region.isValidScreenCrop)
        let wide = DemoEditSeed.targetRegion(for: CGRect(x: 300, y: 300, width: 1200, height: 100), in: visible)
        XCTAssertNil(wide, "an element spanning most of the frame is not worth zooming on")
        XCTAssertNil(DemoEditSeed.targetRegion(for: .zero, in: visible))
    }

    func testCloseZoomsMergeIntoOneMoveAndWideOnesAreDropped() {
        let left = zoom(1, 3, rect: NormalizedRect(x: 0, y: 0.1, width: 0.4, height: 0.4))
        let right = zoom(3.3, 5, rect: NormalizedRect(x: 0.3, y: 0.1, width: 0.4, height: 0.4))
        let merged = DemoEditSeed.merged([right, left])
        XCTAssertEqual(merged.count, 1)
        XCTAssertEqual(merged[0].span, TimeSpan(start: 1, end: 5))
        XCTAssertEqual(merged[0].rect.x, 0.0, accuracy: 1e-9)
        XCTAssertEqual(merged[0].rect.width, 0.7, accuracy: 1e-9)

        let faraway = zoom(10, 12, rect: NormalizedRect(x: 0.6, y: 0.5, width: 0.4, height: 0.4))
        XCTAssertEqual(DemoEditSeed.merged([left, faraway]).count, 2, "a pause between them keeps two moves")

        let tooWide = zoom(3.2, 5, rect: NormalizedRect(x: 0.6, y: 0.6, width: 0.4, height: 0.4))
        XCTAssertEqual(DemoEditSeed.merged([left, tooWide]), [left], "merging would be too wide to be worth it")
    }

    private func spec(steps: [DemoStep]) -> DemoSpec {
        DemoSpec(title: "Demo", startURL: URL(string: "https://app.example.com/")!,
                 allowedOrigins: ["https://app.example.com"], window: WindowSize(width: 1440, height: 900), steps: steps)
    }

    private func clickStep(_ id: String, zoom: ZoomHint = .target) -> DemoStep {
        DemoStep(id: id, action: .click(ElementTarget(candidates: [LocatorCandidate(role: "button", name: id)])),
                 intent: "Click \(id)", zoom: zoom)
    }

    func testSeedZoomsOnTheClickedElementUntilTheNextStepBegins() throws {
        let log = ActionLog(entries: [
            .init(t: 1, stepID: "a", kind: .stepStart),
            .init(t: 1.8, stepID: "a", kind: .stepEnd, rect: CGRect(x: 100, y: 50, width: 100, height: 40)),
            .init(t: 6, stepID: "b", kind: .stepStart),
            .init(t: 6.5, stepID: "b", kind: .stepEnd, rect: CGRect(x: 600, y: 200, width: 100, height: 40))
        ])
        let zooms = DemoEditSeed.zoomSegments(
            spec: spec(steps: [clickStep("a"), clickStep("b", zoom: .none)]),
            log: log, viewport: viewport, recordingDuration: 20
        )
        XCTAssertEqual(zooms.count, 1, "only the step that asked for a zoom gets one")
        XCTAssertEqual(zooms[0].span.start, 0.7, accuracy: 1e-9, "starts just before the pointer arrives")
        XCTAssertEqual(zooms[0].span.end, 5.9, accuracy: 1e-9, "holds through the narration, until the next step")
        XCTAssertTrue(zooms[0].isValid)
    }

    func testSeedOperationsAreOneBatchThatTheDocumentAccepts() throws {
        let log = ActionLog(entries: [
            .init(t: 1, stepID: "a", kind: .stepStart),
            .init(t: 1.8, stepID: "a", kind: .stepEnd, rect: CGRect(x: 100, y: 50, width: 100, height: 40))
        ])
        let line = NarrationLine(at: 1, text: "Open the builder", duration: 3, stepID: "a")
        let operations = DemoEditSeed.operations(
            spec: spec(steps: [clickStep("a")]), log: log, viewport: viewport, narration: [line], recordingDuration: 10
        )
        XCTAssertEqual(operations.count, 2)
        let document = try operations.reduce(edit(10)) { try $0.applying($1) }
        XCTAssertEqual(document.zooms.count, 1)
        XCTAssertEqual(document.narration, [line])
    }

    @MainActor
    func testSeedingIsOneUndoStepAndDoesNotRepeatAfterReopen() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("aura-demo-seed-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let folder = SessionFolder.load(rootURL: root)
        let demo = spec(steps: [clickStep("a")])
        try JSONEncoder().encode(demo).write(to: folder.demoSpecURL)
        try JSONEncoder().encode(viewport).write(to: folder.viewportURL)
        try JSONEncoder().encode(ActionLog(entries: [
            .init(t: 1, stepID: "a", kind: .stepStart),
            .init(t: 1.8, stepID: "a", kind: .stepEnd, rect: CGRect(x: 100, y: 50, width: 100, height: 40))
        ])).write(to: folder.actionLogURL)
        try JSONEncoder().encode([NarrationLine(at: 1, text: "Hello", duration: 2, stepID: "a")]).write(to: folder.narrationLinesURL)

        let store = EditDocumentStore.load(folder: folder, duration: 10, micTimeOffset: 0)
        store.seedDemoEffects(from: folder)
        XCTAssertEqual(store.document.zooms.count, 1)
        XCTAssertEqual(store.document.narration.count, 1)
        XCTAssertTrue(store.document.hasSeededDemoEffects)

        store.undo()
        XCTAssertTrue(store.document.zooms.isEmpty)
        XCTAssertTrue(store.document.narration.isEmpty)
        XCTAssertTrue(store.document.hasSeededDemoEffects, "undoing the polish must not bring it back on the next open")
        store.seedDemoEffects(from: folder)
        XCTAssertTrue(store.document.zooms.isEmpty)
        XCTAssertFalse(store.canUndo)
    }

    // MARK: - Rendering

    func testSourceRegionComposesTheZoomOntoTheCrop() {
        let crop = NormalizedRect(x: 0.1, y: 0.2, width: 0.8, height: 0.6)
        let zoomed = DemoEffectsRenderer.sourceRegion(crop: crop, zoom: NormalizedRect(x: 0.5, y: 0.5, width: 0.5, height: 0.5))
        XCTAssertEqual(zoomed.x, 0.5, accuracy: 1e-9)
        XCTAssertEqual(zoomed.y, 0.5, accuracy: 1e-9)
        XCTAssertEqual(zoomed.width, 0.4, accuracy: 1e-9)
        XCTAssertEqual(zoomed.height, 0.3, accuracy: 1e-9)
        XCTAssertEqual(DemoEffectsRenderer.sourceRegion(crop: crop, zoom: SessionEdit.fullFrame), crop)
    }

    func testRenderPointMapsIntoTheFlippedPlacedPictureAndHidesFarAwayPoints() throws {
        let region = NormalizedRect(x: 0.5, y: 0.5, width: 0.5, height: 0.5)
        let placed = CGRect(x: 0, y: 0, width: 100, height: 100)
        let center = try XCTUnwrap(DemoEffectsRenderer.renderPoint(for: CGPoint(x: 0.75, y: 0.75), region: region, placed: placed))
        XCTAssertEqual(center, CGPoint(x: 50, y: 50))
        let topLeft = try XCTUnwrap(DemoEffectsRenderer.renderPoint(for: CGPoint(x: 0.5, y: 0.5), region: region, placed: placed))
        XCTAssertEqual(topLeft, CGPoint(x: 0, y: 100), "top of the region is the top of the picture, which is high y in Core Image")
        XCTAssertNil(DemoEffectsRenderer.renderPoint(for: CGPoint(x: 0.1, y: 0.1), region: region, placed: placed))
    }

    func testZoomCutsTheQuadrantFromTheSourceAtOutputResolution() throws {
        // Four coloured quadrants. Zooming onto the top-right one must fill the frame with it.
        let size = CGSize(width: 100, height: 100)
        func quadrant(_ x: Double, _ y: Double, _ color: CIColor) -> CIImage {
            CIImage(color: color).cropped(to: CGRect(x: x, y: y, width: 50, height: 50))
        }
        let image = quadrant(0, 50, CIColor(red: 1, green: 0, blue: 0))        // top-left, red
            .composited(over: quadrant(50, 50, CIColor(red: 0, green: 1, blue: 0)))  // top-right, green
            .composited(over: quadrant(0, 0, CIColor(red: 0, green: 0, blue: 1)))   // bottom-left, blue
            .composited(over: quadrant(50, 0, CIColor(red: 1, green: 1, blue: 0)))   // bottom-right, yellow
        let result = CoreImagePiPCompositor.screenImage(
            image, crop: nil, zoom: NormalizedRect(x: 0.5, y: 0, width: 0.5, height: 0.5), renderSize: size
        )
        let context = CIContext(options: [.useSoftwareRenderer: true])
        for point in [CGPoint(x: 5, y: 5), CGPoint(x: 95, y: 95), CGPoint(x: 50, y: 50)] {
            var pixel = [UInt8](repeating: 0, count: 4)
            context.render(result, toBitmap: &pixel, rowBytes: 4,
                           bounds: CGRect(x: point.x, y: point.y, width: 1, height: 1),
                           format: .RGBA8, colorSpace: CGColorSpaceCreateDeviceRGB())
            XCTAssertEqual(pixel, [0, 255, 0, 255], "every corner of the output is the zoomed quadrant")
        }
    }

    private func pixel(_ image: CIImage, at point: CGPoint) -> [UInt8] {
        var pixel = [UInt8](repeating: 0, count: 4)
        CIContext(options: [.useSoftwareRenderer: true]).render(
            image, toBitmap: &pixel, rowBytes: 4, bounds: CGRect(x: point.x, y: point.y, width: 1, height: 1),
            format: .RGBA8, colorSpace: CGColorSpaceCreateDeviceRGB())
        return pixel
    }

    func testTheCursorIsDrawnWithItsTipOnThePointAndRipplesSpreadAroundClicks() throws {
        let size = CGSize(width: 1000, height: 1000)
        let background = CIImage(color: CIColor(red: 0.5, green: 0.5, blue: 0.5)).cropped(to: CGRect(origin: .zero, size: size))
        let log = ActionLog(entries: [
            .init(t: 1, stepID: "a", kind: .mouseMove, point: CGPoint(x: 400, y: 150)),
            .init(t: 2, stepID: "a", kind: .mouseDown, point: CGPoint(x: 400, y: 150))
        ])
        let path = CursorPath(log: log, viewport: viewport)
        let timeMap = TimeMap(clips: [TimelineClip(source: TimeSpan(start: 0, end: 10))])
        func draw(at time: TimeInterval, style: CursorStyle) -> CIImage {
            DemoEffectsRenderer.drawCursor(
                over: background, placed: background.extent, crop: SessionEdit.fullFrame, zoom: SessionEdit.fullFrame,
                effects: ResolvedDemoEffects(zooms: [], cursor: path, cursorStyle: style, timeMap: timeMap),
                sessionTime: time, renderSize: size
            )
        }

        // The pointer is at (0.5, 0.5) of the source, so the tip lands mid-picture. The arrow's
        // body hangs down and to the right of the tip (down is low y in Core Image).
        let withCursor = draw(at: 1.5, style: CursorStyle(visible: true, scale: 1, ripple: false))
        XCTAssertEqual(pixel(withCursor, at: CGPoint(x: 100, y: 100)), [128, 128, 128, 255], "far from it, untouched")
        let body = pixel(withCursor, at: CGPoint(x: 506, y: 484))
        XCTAssertLessThan(body[0], 60, "the arrow's body is dark")

        // Ripple: spreads around the click, and is gone after its duration.
        let ring = CGPoint(x: 500 + 49, y: 500)
        let during = pixel(draw(at: 2.25, style: CursorStyle(visible: true, scale: 1, ripple: true)), at: ring)
        let without = pixel(draw(at: 2.25, style: CursorStyle(visible: true, scale: 1, ripple: false)), at: ring)
        XCTAssertGreaterThan(Int(during[2]) - Int(during[0]), Int(without[2]) - Int(without[0]) + 20, "the ring tints the picture blue")
        let after = pixel(draw(at: 2.6, style: CursorStyle(visible: true, scale: 1, ripple: true)), at: ring)
        XCTAssertEqual(after, pixel(draw(at: 2.6, style: CursorStyle(visible: true, scale: 1, ripple: false)), at: ring))
    }

    // MARK: - Timeline and composition

    private func probe(_ kind: TrackKind) -> SourceTrackProbe {
        SourceTrackProbe(url: URL(fileURLWithPath: "/demo-effects-test.mov"), kind: kind,
                         duration: Timeline.time(seconds: 10),
                         displaySize: CGSize(width: 2000, height: 1000), preferredTransform: .identity)
    }

    func testEffectsOnlyExistWhereThereIsAScreenToDrawOn() throws {
        let path = CursorPath(log: ActionLog(entries: [.init(t: 1, stepID: "a", kind: .mouseMove, point: CGPoint(x: 1, y: 1))]), viewport: viewport)
        let document = try edit(10).applying(.setZoom(zoom(1, 4)))

        let screen = TimelineResolver.resolve(document: document, probes: [probe(.screen)], cursorPath: path)
        XCTAssertEqual(screen.effects?.zooms.count, 1)
        XCTAssertNotNil(screen.effects?.cursor)
        XCTAssertFalse(screen.canUseLayerInstructions, "needs the Core Image compositor")

        let cameraOnly = TimelineResolver.resolve(document: document, probes: [probe(.camera)], cursorPath: path)
        XCTAssertNil(cameraOnly.effects, "a camera promoted to the base has nothing to draw on")

        let plain = TimelineResolver.resolve(document: edit(10), probes: [probe(.screen)])
        XCTAssertNil(plain.effects)
        XCTAssertTrue(plain.canUseLayerInstructions, "an ordinary recording keeps the cheap path")

        let hidden = try document.applying(.setCursorStyle(CursorStyle(visible: false)))
        XCTAssertNil(TimelineResolver.resolve(document: hidden, probes: [probe(.screen)], cursorPath: path).effects?.cursor)
    }

    func testOnlyNarrationWithAClipOnDiskIsResolved() throws {
        let line = NarrationLine(at: 1, text: "Hi", duration: 2)
        let document = try edit(10).applying(.setNarration(line))
        XCTAssertTrue(TimelineResolver.resolve(document: document, probes: [probe(.screen)]).narration.isEmpty)
        let url = URL(fileURLWithPath: "/clip.m4a")
        let resolved = TimelineResolver.resolve(document: document, probes: [probe(.screen)], narrationClips: [line.id: url])
        XCTAssertEqual(resolved.narration, [ResolvedNarration(id: line.id, url: url, at: 1, duration: Timeline.time(seconds: 2))])
    }

    @MainActor
    func testNarrationAndEffectsBuildARealCompositionAndCutsTrimTheClip() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("aura-demo-comp-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let folder = SessionFolder.load(rootURL: root)
        let clip = root.appendingPathComponent("line.m4a")
        try await TestMedia.writeVideo(to: folder.screenURL, seconds: 6)
        try TestMedia.writeSilentAudio(to: clip, seconds: 3)
        try Data(#"{"ts":0,"type":"record_start","media_ts":0}"#.utf8).write(to: folder.eventsURL)

        let line = NarrationLine(at: 1, text: "Hello there", duration: 3)
        var document = try SessionEdit.initial(duration: 6)
            .applying(.setNarration(line))
            .applying(.setZoom(zoom(1, 4)))
        let probes = await SourceTrackProbe.probeAll(in: folder)
        let builder = LayerInstructionCompositionBuilder()

        func audioSeconds(_ built: BuiltComposition) async throws -> Double {
            var total = 0.0
            for track in try await built.asset.loadTracks(withMediaType: .audio) {
                total += try await track.load(.segments).filter { !$0.isEmpty }
                    .reduce(0) { $0 + CMTimeGetSeconds($1.timeMapping.target.duration) }
            }
            return total
        }

        var built = try await builder.build(
            TimelineResolver.resolve(document: document, probes: probes, narrationClips: [line.id: clip]))
        let untrimmed = try await audioSeconds(built)
        XCTAssertEqual(untrimmed, 3, accuracy: 0.05)
        let instructions = try XCTUnwrap(built.videoComposition?.instructions as? [PiPCompositionInstruction])
        XCTAssertTrue(instructions.allSatisfy { $0.effects != nil && $0.containsTweening })

        // A cut inside the line trims the clip rather than leaving a gap or shifting the rest.
        document = try document.applying(.removeRange(TimeSpan(start: 2, end: 3)))
        built = try await builder.build(
            TimelineResolver.resolve(document: document, probes: probes, narrationClips: [line.id: clip]))
        let trimmed = try await audioSeconds(built)
        XCTAssertEqual(trimmed, 2, accuracy: 0.05)
        XCTAssertEqual(built.duration.seconds, 5, accuracy: 0.05)
    }
}
