import XCTest
@testable import Aura

final class BrowserSpecTests: XCTestCase {
    private var temporaryDirectory: URL {
        ProcessInfo.processInfo.environment["TMPDIR"].map { URL(fileURLWithPath: $0) } ?? FileManager.default.temporaryDirectory
    }

    private func spec() -> DemoSpec {
        DemoSpec(title: "Build a chatbot", startURL: URL(string: "https://example.com/dashboard")!,
                 allowedOrigins: ["https://example.com"], window: WindowSize(width: 1440, height: 900),
                 parameters: ["site_url": "https://example.org"], steps: [
                    .init(id: "s1", action: .handover(reason: .login, doneWhen: Expectation(visible: .init(role: "button", name: "New agent"))), intent: "Sign in"),
                    .init(id: "s2", action: .click(.init(candidates: [.init(testId: "new-agent"), .init(role: "button", name: "New agent")])), intent: "Open builder", expect: Expectation(url: "/agents/new"), narration: "Create an agent.", zoom: .target, emphasis: .ripple),
                    .init(id: "s3", action: .fill(.init(candidates: [.init(role: "textbox", name: "Website")]), value: .parameter("site_url")), intent: "Enter website")
                 ])
    }

    func testLLDExampleHasFlatActionJSONAndRoundTrips() throws {
        let original = spec()
        let data = try JSONEncoder().encode(original)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(json["format"] as? String, "aura-demo/v1")
        let steps = try XCTUnwrap(json["steps"] as? [[String: Any]])
        XCTAssertEqual(steps[1]["action"] as? String, "click")
        XCTAssertNotNil(steps[1]["target"])
        XCTAssertEqual((steps[2]["value"] as? [String: String])?["parameter"], "site_url")
        XCTAssertFalse(String(decoding: data, as: UTF8.self).contains("_0"))
        XCTAssertEqual(try JSONDecoder().decode(DemoSpec.self, from: data), original)
    }

    func testRootAndTargetedScrollSpecsRoundTripAndValidate() throws {
        let old = Data(#"{"action":"scroll","to":{"x":12,"y":640}}"#.utf8)
        XCTAssertEqual(try JSONDecoder().decode(DemoAction.self, from: old), .scroll(to: .init(x: 12, y: 640)))
        var demo = spec()
        let target = ElementTarget(candidates: [.init(testId: "panel"), .init(css: "#panel")])
        demo.steps.append(.init(id: "scroll", action: .scroll(to: .init(x: 25, y: 400, target: target)), intent: "Scroll panel"))
        try demo.validate()
        XCTAssertEqual(try JSONDecoder().decode(DemoSpec.self, from: JSONEncoder().encode(demo)), demo)
        demo.steps[3].action = .scroll(to: .init(x: 0, y: 1, target: .init(candidates: [.init(css: "iframe")])))
        XCTAssertThrowsError(try demo.validate())
    }

    func testAllActionShapesRoundTrip() throws {
        let target = ElementTarget(candidates: [.init(text: "Create")])
        let actions: [DemoAction] = [.goto(URL(string: "https://example.com/new")!), .click(target),
            .fill(target, value: .literal("Website")), .press(key: "Enter"), .scroll(to: .init(x: 0, y: 640)),
            .wait(seconds: 0.4), .handover(reason: .manual, doneWhen: nil)]
        for action in actions {
            let data = try JSONEncoder().encode(action)
            XCTAssertEqual(try JSONDecoder().decode(DemoAction.self, from: data), action)
        }
        let hint = ZoomHint.region(.init(x: 0.1, y: 0.2, width: 0.3, height: 0.4))
        XCTAssertEqual(try JSONDecoder().decode(ZoomHint.self, from: JSONEncoder().encode(hint)), hint)
    }

    func testDefaultsAndUnknownDiscriminators() throws {
        let raw = #"{"id":"s1","action":"wait","seconds":0,"intent":"Wait"}"#.data(using: .utf8)!
        let step = try JSONDecoder().decode(DemoStep.self, from: raw)
        XCTAssertEqual(step.zoom, .none); XCTAssertEqual(step.emphasis, .none)
        for action in ["evaluate", "runScript", "unknown"] {
            XCTAssertThrowsError(try JSONDecoder().decode(DemoAction.self, from: Data("{\"action\":\"\(action)\"}".utf8)))
        }
        XCTAssertThrowsError(try JSONDecoder().decode(InputValue.self, from: Data(#"{"literal":"a","parameter":"b"}"#.utf8)))
    }

    func testLoadValidationRejectsUnsafeURLsOriginsAndSizes() throws {
        var cases: [DemoSpec] = []
        for raw in ["file:///tmp/demo", "javascript:alert(1)", "data:text/html,hi", "https://user:secret@example.com", "https://evil.com"] {
            var s = spec(); s.startURL = URL(string: raw)!; cases.append(s)
        }
        for origins in [["https://example.com/path"], ["*"], [], ["https://example.com", "https://EXAMPLE.com:443"]] {
            var s = spec(); s.allowedOrigins = origins; cases.append(s)
        }
        var s = spec(); s.window.width = 100000; cases.append(s)
        s = spec(); s.steps.append(s.steps[0]); cases.append(s)
        s = spec(); s.parameters = [:]; cases.append(s)
        s = spec(); s.steps[0].action = .wait(seconds: -1); cases.append(s)
        s = spec(); s.steps[0].action = .goto(URL(string: "https://evil.com")!); cases.append(s)
        s = spec(); s.steps[0].expect = Expectation(url: "//evil.com"); cases.append(s)
        s = spec(); s.steps[0].expect = Expectation(); cases.append(s)
        s = spec(); s.steps[0].action = .click(.init(candidates: [.init(css: "iframe >> button")])); cases.append(s)
        s = spec(); s.steps[0].action = .click(.init(candidates: [.init(text: "A", css: "button")])); cases.append(s)
        for invalid in cases {
            XCTAssertThrowsError(try JSONDecoder().decode(DemoSpec.self, from: JSONEncoder().encode(invalid)))
        }
    }

    func testUnknownFormatAndNonFiniteGeometryAreRejected() throws {
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(spec())) as? [String: Any])
        json["format"] = "aura-demo/v99"
        XCTAssertThrowsError(try JSONDecoder().decode(DemoSpec.self, from: JSONSerialization.data(withJSONObject: json)))
        var s = spec()
        s.steps[0].action = .scroll(to: .init(x: .nan, y: 0))
        XCTAssertThrowsError(try s.validate())
        s = spec(); s.steps[0].zoom = .region(.init(x: 0.9, y: 0, width: 0.5, height: 0.5))
        XCTAssertThrowsError(try s.validate())
    }

    func testParameterResolutionDoesNotChangeStoredSpec() throws {
        let original = spec()
        let resolved = try original.steps[2].action.resolved(parameters: original.parameters)
        guard case .fill(_, let value) = resolved else { return XCTFail("Expected fill") }
        XCTAssertEqual(value, .literal("https://example.org"))
        guard case .fill(_, let stored) = original.steps[2].action else { return XCTFail("Expected fill") }
        XCTAssertEqual(stored, .parameter("site_url"))
        XCTAssertThrowsError(try original.steps[2].action.resolved(parameters: [:]))
    }

    func testStoreBumpsRevisionAndCopiesExactSpecWithoutProfile() throws {
        let root = temporaryDirectory.appendingPathComponent("browser-spec-\(UUID())")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = DemoSpecStore(rootDirectory: root.appendingPathComponent("specs"))
        let original = spec(), first = try store.save(original)
        XCTAssertEqual(first.revision, 1)
        XCTAssertEqual(original.revision, 0)
        XCTAssertEqual(try store.load(id: first.id), first)
        let second = try store.save(first)
        XCTAssertEqual(second.revision, 2)
        XCTAssertThrowsError(try store.save(first))
        try store.copy(first, into: root)
        XCTAssertEqual(try store.load(from: root.appendingPathComponent("demo-spec.json")), first)
        XCTAssertFalse(FileManager.default.fileExists(atPath: root.appendingPathComponent("profile").path))
    }

    func testStoreBoundsFileReadsAndChecksFolderIdentity() throws {
        let root = temporaryDirectory.appendingPathComponent("browser-spec-\(UUID())")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = DemoSpecStore(rootDirectory: root)
        let url = root.appendingPathComponent("oversized.json")
        try Data(repeating: 32, count: DemoSpec.maximumBytes + 1).write(to: url)
        XCTAssertThrowsError(try store.load(from: url))
        let wrongID = UUID()
        try FileManager.default.createDirectory(at: store.directory(for: wrongID), withIntermediateDirectories: true)
        try JSONEncoder().encode(spec()).write(to: store.directory(for: wrongID).appendingPathComponent("spec.json"))
        XCTAssertThrowsError(try store.load(id: wrongID))
    }
}
