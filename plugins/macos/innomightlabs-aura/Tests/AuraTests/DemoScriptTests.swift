import XCTest
@testable import Aura

final class DemoScriptTests: XCTestCase {
    private func target(_ name: String) -> ElementTarget {
        ElementTarget(candidates: [LocatorCandidate(role: "button", name: name), LocatorCandidate(css: "#secret-internal-id")],
                      hintRect: BrowserRect(x: 9, y: 9, width: 9, height: 9))
    }

    private func spec() -> DemoSpec {
        DemoSpec(
            title: "Demo", startURL: URL(string: "https://app.example.com/private/path?token=abc")!,
            allowedOrigins: ["https://app.example.com"], window: WindowSize(width: 1440, height: 900),
            parameters: ["site": "https://customer.example.com"], steps: [
                DemoStep(id: "login", action: .handover(reason: .login, doneWhen: nil), intent: "Sign in"),
                DemoStep(id: "create", action: .click(target("Create agent")), intent: "Click “Create agent”"),
                DemoStep(id: "site", action: .fill(ElementTarget(candidates: [LocatorCandidate(role: "textbox", name: "Website")]),
                                                   value: .parameter("site")), intent: "Fill in “Website”"),
                DemoStep(id: "wait", action: .wait(seconds: 2), intent: "Pause")
            ])
    }

    // MARK: - What the agent is told

    func testThePromptNamesTheStepsButNeverValuesOrInternals() {
        let prompt = DemoScriptPrompt.build(spec: spec(), instruction: "Friendly, under a minute")
        XCTAssertTrue(prompt.contains("\"id\":\"create\""))
        XCTAssertTrue(prompt.contains("clicks “Create agent”"))
        XCTAssertTrue(prompt.contains("fills in “Website”"))
        XCTAssertTrue(prompt.contains("Friendly, under a minute"))
        XCTAssertTrue(prompt.contains("https://app.example.com"), "the site's origin")
        for secret in ["customer.example.com", "token=abc", "private/path", "secret-internal-id", "hintRect"] {
            XCTAssertFalse(prompt.contains(secret), "\(secret) must never reach the agent")
        }
    }

    func testThePromptHasADefaultBriefAndAVeryLongDemoExceedsTheMessageCap() {
        XCTAssertTrue(DemoScriptPrompt.build(spec: spec(), instruction: "  ").contains("about a minute long"))
        var long = spec()
        long.steps = (0..<700).map { DemoStep(id: "s\($0)", action: .click(target("Button \($0)")), intent: "Click “Button \($0)”") }
        XCTAssertGreaterThan(DemoScriptPrompt.build(spec: long, instruction: "x").count, InnomightLabsEditSuggester.maximumMessageCharacters,
                             "a demo too long to script in one message is refused by the caller, not truncated here")
    }

    // MARK: - What is applied

    private func reply(_ json: String) -> String { "Here is a script.\n```json\n\(json)\n```" }

    func testWordingAndEmphasisAreAppliedAndActionsNeverChange() {
        let before = spec()
        let result = DemoScriptParser.apply(reply("""
        {"title":"Build a chatbot","intro":"Let's give your site an assistant.","outro":"That's it.",
         "steps":[{"id":"create","intent":"Start a new agent","narration":"Start by creating an agent.","zoom":"target","emphasis":"ripple"},
                  {"id":"site","narration":"Paste in your website.","zoom":"target"}]}
        """), to: before)
        XCTAssertEqual(result.notes, [])
        XCTAssertEqual(result.spec.title, "Build a chatbot")
        XCTAssertEqual(result.spec.intro, "Let's give your site an assistant.")
        XCTAssertEqual(result.spec.outro, "That's it.")
        let create = result.spec.steps[1]
        XCTAssertEqual(create.intent, "Start a new agent")
        XCTAssertEqual(create.narration, "Start by creating an agent.")
        XCTAssertEqual(create.zoom, .target)
        XCTAssertEqual(create.emphasis, .ripple)
        XCTAssertEqual(result.spec.steps[2].narration, "Paste in your website.")

        XCTAssertEqual(result.spec.steps.map(\.action), before.steps.map(\.action), "what the user did is untouched")
        XCTAssertEqual(result.spec.steps.map(\.id), before.steps.map(\.id))
        XCTAssertEqual(result.spec.steps.map(\.expect), before.steps.map(\.expect))
        XCTAssertEqual(result.spec.parameters, before.parameters)
        XCTAssertEqual(result.spec.allowedOrigins, before.allowedOrigins)
        XCTAssertEqual(result.spec.startURL, before.startURL)
        XCTAssertNoThrow(try result.spec.validate())
    }

    func testAnAgentCannotAddRemoveOrReorderSteps() {
        let before = spec()
        let result = DemoScriptParser.apply(reply("""
        {"steps":[{"id":"invented","narration":"Delete everything.","action":"goto"},
                  {"id":"create","narration":"Real.","action":"click","target":{"candidates":[{"css":"#evil"}]}}]}
        """), to: before)
        XCTAssertEqual(result.spec.steps.map(\.action), before.steps.map(\.action))
        XCTAssertEqual(result.spec.steps.map(\.id), before.steps.map(\.id))
        XCTAssertEqual(result.spec.steps[1].narration, "Real.")
        XCTAssertEqual(result.notes.count, 1)
        XCTAssertTrue(result.notes[0].contains("invented"))
    }

    func testAHandoverIsNeverNarratedAndAZoomNeedsAnElement() {
        let result = DemoScriptParser.apply(reply("""
        {"steps":[{"id":"login","narration":"Now type your password.","zoom":"target"},
                  {"id":"wait","zoom":"target"}]}
        """), to: spec())
        XCTAssertNil(result.spec.steps[0].narration)
        XCTAssertEqual(result.spec.steps[0].zoom, ZoomHint.none)
        XCTAssertEqual(result.spec.steps[3].zoom, ZoomHint.none)
        XCTAssertEqual(result.notes.count, 3)
    }

    func testEmptyNarrationClearsAndOverlongTextIsIgnored() {
        var start = spec()
        start.steps[1].narration = "Old words."
        start.intro = "Old intro."
        let cleared = DemoScriptParser.apply(reply(#"{"intro":"","steps":[{"id":"create","narration":""}]}"#), to: start)
        XCTAssertNil(cleared.spec.steps[1].narration)
        XCTAssertNil(cleared.spec.intro)

        let long = String(repeating: "word ", count: 300)
        let ignored = DemoScriptParser.apply(reply(#"{"outro":"\#(long)","steps":[{"id":"create","narration":"\#(long)"}]}"#), to: start)
        XCTAssertEqual(ignored.spec.steps[1].narration, "Old words.", "too long is ignored, not truncated")
        XCTAssertNil(ignored.spec.outro)
        XCTAssertEqual(ignored.notes.count, 2)
    }

    func testRepliesWithoutAUsableScriptChangeNothing() {
        let before = spec()
        for text in ["Which tone would you like?", "```json\n[1,2,3]\n```", "{not json", "```json\n{\"steps\":\"nope\"}\n```"] {
            let result = DemoScriptParser.apply(text, to: before)
            XCTAssertEqual(result.spec, before, text)
            XCTAssertFalse(result.notes.isEmpty, text)
        }
        XCTAssertEqual(DemoScriptParser.apply("Which tone would you like?", to: before).reply, "Which tone would you like?")
    }

    func testABareJSONObjectAndProseAroundItAreBothAccepted() {
        let result = DemoScriptParser.apply(#"Sure! {"intro":"Hello there.","steps":[]} Anything else?"#, to: spec())
        XCTAssertEqual(result.spec.intro, "Hello there.")
        XCTAssertEqual(result.spec.steps, spec().steps)
    }

    func testNoneIsAcceptedForEmphasisAndZoomAndUnknownValuesAreIgnored() {
        var start = spec()
        start.steps[1].zoom = .target
        start.steps[1].emphasis = .ripple
        let result = DemoScriptParser.apply(reply(#"{"steps":[{"id":"create","zoom":"none","emphasis":"none"},{"id":"site","zoom":"huge","emphasis":"sparkle"}]}"#), to: start)
        XCTAssertEqual(result.spec.steps[1].zoom, ZoomHint.none)
        XCTAssertEqual(result.spec.steps[1].emphasis, ClickEmphasis.none)
        XCTAssertEqual(result.spec.steps[2].zoom, ZoomHint.none, "an unknown value changes nothing")
    }

    // MARK: - Polish by instruction, in the review window

    func testTheAgentCanProposeEveryDemoOperationAndTheParserKeepsThem() throws {
        let zoomID = UUID(), lineID = UUID()
        let text = """
        I'll zoom in on the click and rewrite the intro.
        ```json
        [{"op":"set_zoom","start":4,"end":7,"rect":{"x":0.5,"y":0.1,"width":0.4,"height":0.4},"why":"The button is small."},
         {"op":"remove_zooms","ids":["\(zoomID.uuidString)"]},
         {"op":"set_cursor_style","scale":1.5,"ripple":false,"why":"Bigger pointer."},
         {"op":"set_narration","id":"\(lineID.uuidString)","t":1,"text":"A shorter opening.","why":"Tighter."},
         {"op":"remove_narration","ids":["\(lineID.uuidString)"]}]
        ```
        """
        let result = EditSuggestionParser.parse(text)
        XCTAssertEqual(result.suggestions.count, 5)
        XCTAssertEqual(result.suggestions[0].rationale, "The button is small.")
        guard case .setNarration(let line) = result.suggestions[3].operation else { return XCTFail("Expected narration") }
        XCTAssertTrue(line.isDraft, "a rewrite is a draft until it has been spoken")
        XCTAssertEqual(line.id, lineID)
        XCTAssertThrowsError(try SessionEdit.initial(duration: 10).applying(.setNarration(line))) {
            XCTAssertEqual($0 as? EditOperationError, .narrationNotRendered)
        }
    }

    func testTheDigestTellsTheAgentWhatWasDoneAndHowItIsDressed() throws {
        var document = SessionEdit.initial(duration: 20)
        document = try document.applying(.setZoom(ZoomSegment(span: TimeSpan(start: 4, end: 7), rect: NormalizedRect(x: 0.5, y: 0, width: 0.5, height: 0.5))))
        document = try document.applying(.setNarration(NarrationLine(at: 1, text: "Welcome.", duration: 2)))
        let steps = [SessionDigest.DemoStepSpan(id: "create", intent: "Click “Create”", span: TimeSpan(start: 3, end: 8))]
        let digest = SessionDigest.make(sessionID: "s", duration: 20, probes: [], events: EventTimeline(events: []),
                                        document: document, transcript: nil, demoSteps: steps)
        let demo = try XCTUnwrap(digest.demo)
        XCTAssertEqual(demo.steps.map(\.id), ["create"])
        XCTAssertEqual(demo.zooms.first?.rect, [0.5, 0, 0.5, 0.5])
        XCTAssertEqual(demo.narration.first?.text, "Welcome.")
        XCTAssertEqual(demo.cursor, .standard)

        let plain = SessionDigest.make(sessionID: "s", duration: 20, probes: [], events: EventTimeline(events: []),
                                       document: SessionEdit.initial(duration: 20), transcript: nil)
        XCTAssertNil(plain.demo, "an ordinary recording's digest is unchanged")
        XCTAssertFalse(String(data: try JSONEncoder().encode(plain), encoding: .utf8)!.contains("demo"))
    }

    func testTheDigestStaysBoundedForAHugeDemo() throws {
        var document = SessionEdit.initial(duration: 1_000)
        for index in 0..<100 {
            document = try document.applying(.setZoom(ZoomSegment(
                span: TimeSpan(start: Double(index) * 9, end: Double(index) * 9 + 2),
                rect: NormalizedRect(x: 0, y: 0, width: 0.5, height: 0.5))))
        }
        let steps = (0..<100).map { SessionDigest.DemoStepSpan(id: "s\($0)", intent: String(repeating: "long ", count: 80), span: TimeSpan(start: Double($0), end: Double($0) + 1)) }
        let digest = SessionDigest.make(sessionID: "s", duration: 1_000, probes: [], events: EventTimeline(events: []),
                                        document: document, transcript: nil, demoSteps: steps)
        let demo = try XCTUnwrap(digest.demo)
        XCTAssertEqual(demo.steps.count, SessionDigest.maxDemoEntries)
        XCTAssertEqual(demo.zooms.count, SessionDigest.maxDemoEntries)
        XCTAssertGreaterThan(demo.omitted, 0, "the agent is told the lists are partial")
        XCTAssertTrue(demo.steps.allSatisfy { $0.intent.count <= 120 })
    }

    @MainActor
    func testStepSpansAreReadFromTheTakeAndEachRunsUntilTheNextBegins() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("aura-step-spans-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let folder = SessionFolder.load(rootURL: root)
        try JSONEncoder().encode(spec()).write(to: folder.demoSpecURL)
        try JSONEncoder().encode(ActionLog(entries: [
            .init(t: 1, stepID: "create", kind: .stepStart), .init(t: 2, stepID: "create", kind: .stepEnd),
            .init(t: 6, stepID: "site", kind: .stepStart), .init(t: 7, stepID: "site", kind: .stepEnd)
        ])).write(to: folder.actionLogURL)
        let spans = ReviewViewModel.loadDemoSteps(from: folder)
        XCTAssertEqual(spans.map(\.id), ["create", "site"])
        XCTAssertEqual(spans[0].span, TimeSpan(start: 1, end: 6), "the narration plays after the action, until the next step")
        XCTAssertEqual(spans[1].span, TimeSpan(start: 6, end: 7))
        XCTAssertTrue(ReviewViewModel.loadDemoSteps(from: SessionFolder.load(rootURL: root.appendingPathComponent("nothing"))).isEmpty)
    }
}
