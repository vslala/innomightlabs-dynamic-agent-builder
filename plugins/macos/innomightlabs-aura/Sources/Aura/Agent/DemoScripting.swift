import Foundation

struct DemoScriptResult: Equatable, Sendable {
    /// The spec with the agent's wording applied. Its actions are exactly the ones it was given.
    let spec: DemoSpec
    /// What the agent proposed that was not used, and why, in words the user can read.
    let notes: [String]
    /// What the agent said around the script, for when it asked a question instead of writing one.
    let reply: String
}

/// The seam the demo editor talks to. `InnomightLabsDemoScripter` is the real one; tests substitute
/// their own.
protocol DemoScripting: Sendable {
    func writeScript(for spec: DemoSpec, instruction: String) async throws -> DemoScriptResult
}

/// Writes the words of a demo, and nothing else.
///
/// The agent sees what the user did described in words (never typed values, page content or
/// credentials), and may change only wording and emphasis. That is the guarantee the whole feature
/// rests on: every action in a take was performed by the user, not proposed by a model.
enum DemoScriptPrompt {
    /// What the model gets, and nothing more. Deliberately without values, parameters' contents,
    /// locator internals or URLs beyond the origin.
    static func build(spec: DemoSpec, instruction: String) -> String {
        let steps = spec.steps.map { step -> String in
            var line = "{\"id\":\(json(step.id)),\"does\":\(json(describe(step.action))),\"intent\":\(json(step.intent))"
            if let narration = step.narration, !narration.isEmpty { line += ",\"narration\":\(json(narration))" }
            return line + "}"
        }.joined(separator: ",\n  ")
        let origin = (try? DemoSpec.origin(of: spec.startURL)) ?? "a website"
        let brief = instruction.trimmingCharacters(in: .whitespacesAndNewlines)

        return """
        You write the voice-over for a screen-recorded product demo. A person already did the flow in a
        browser; you are given the steps they took and write what the narrator says as each happens.

        You may change only words and emphasis. You cannot add, remove, reorder or change a step, and
        you are never told what was typed. Reply with ONE JSON object in a ```json fenced block, after
        at most two sentences of your own.

        {"title":"<short title>","intro":"<spoken before the first step>","outro":"<spoken after the last>",
         "steps":[{"id":"<id copied from below>","intent":"<short label>","narration":"<spoken during this step>",
                   "zoom":"target"|"none","emphasis":"ripple"|"none"}]}

        RULES
        - Copy each step id exactly. A step you leave out keeps what it has.
        - Narration is speech for a viewer, not a description of the mouse. "Now let's give your site its own
          assistant" is good; "Click the New agent button" is not. One or two short sentences a step, about
          2.5 spoken words per second of what happens.
        - A step with "does":"sign in yourself" is the viewer waiting for the narrator to step out: give it no
          narration.
        - "zoom":"target" magnifies the element the step clicks or fills; use it where the viewer needs to see
          a small control or a result, and "none" elsewhere. Zoom a third of the steps at most.
        - "emphasis":"ripple" shows a ripple where a click lands, and clicks have it by default. Use "none" on
          the small clicks that are not worth the viewer's attention, so the ones that matter stand out.
        - Never include a password, email address, token, or anything you were not shown.

        THE DEMO
        site: \(origin)
        title so far: \(json(spec.title))
        intro so far: \(json(spec.intro ?? ""))
        outro so far: \(json(spec.outro ?? ""))
        steps:
          \(steps)

        WHAT THE USER WANTS
        \(brief.isEmpty ? "A clear, friendly walkthrough, about a minute long." : brief)
        """
    }

    private static func describe(_ action: DemoAction) -> String {
        switch action {
        case .goto: return "opens a page"
        case .click(let target): return "clicks \(DemonstrationCapture.name(of: target))"
        case .fill(let target, _): return "fills in \(DemonstrationCapture.name(of: target))"
        case .press(let key): return "presses \(key)"
        case .scroll: return "scrolls"
        case .wait(let seconds): return "waits \(Int(seconds)) seconds"
        case .handover: return "sign in yourself"
        }
    }

    private static func json(_ value: String) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: [value]), let text = String(data: data, encoding: .utf8) else { return "\"\"" }
        return String(text.dropFirst().dropLast())
    }
}

/// Reads the agent's reply and applies only what is allowed.
///
/// Pure and defensive: the reply is free text from a model. Anything that is not wording or
/// emphasis for a step that exists is dropped and reported, never applied and never guessed at.
enum DemoScriptParser {
    static let maximumLineCharacters = 600
    static let maximumTitleCharacters = 120

    private struct Reply: Decodable {
        struct Step: Decodable {
            var id: String?
            var intent: String?
            var narration: String?
            var zoom: String?
            var emphasis: String?
        }
        var title: String?
        var intro: String?
        var outro: String?
        var steps: [Step]?
    }

    static func apply(_ reply: String, to spec: DemoSpec) -> DemoScriptResult {
        let prose = reply.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let payload = jsonObject(in: reply), let decoded = try? JSONDecoder().decode(Reply.self, from: payload) else {
            return DemoScriptResult(spec: spec, notes: ["The agent did not send a script, so nothing changed."], reply: prose)
        }

        var result = spec
        var notes: [String] = []

        func line(_ text: String?, _ what: String) -> String?? {
            guard let text else { return nil }
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard trimmed.count <= maximumLineCharacters else {
                notes.append("Ignored the \(what): it was longer than \(maximumLineCharacters) characters.")
                return nil
            }
            return .some(trimmed.isEmpty ? nil : trimmed)
        }

        if let title = decoded.title?.trimmingCharacters(in: .whitespacesAndNewlines), !title.isEmpty {
            if title.count <= maximumTitleCharacters { result.title = title }
            else { notes.append("Ignored the title: it was too long.") }
        }
        if let intro = line(decoded.intro, "intro") { result.intro = intro }
        if let outro = line(decoded.outro, "outro") { result.outro = outro }

        for proposed in decoded.steps ?? [] {
            guard let id = proposed.id, let index = result.steps.firstIndex(where: { $0.id == id }) else {
                notes.append("Ignored a step the demo does not have: \(proposed.id ?? "(no id)").")
                continue
            }
            let isHandover: Bool = { if case .handover = result.steps[index].action { return true } else { return false } }()
            let hasTarget: Bool = {
                switch result.steps[index].action { case .click, .fill: return true; default: return false }
            }()

            if let intent = proposed.intent?.trimmingCharacters(in: .whitespacesAndNewlines), !intent.isEmpty, intent.count <= 200 {
                result.steps[index].intent = intent
            }
            if let narration = line(proposed.narration, "narration for \(id)") {
                if isHandover { notes.append("Ignored narration for \(id): the viewer is waiting while the user signs in.") }
                else { result.steps[index].narration = narration }
            }
            switch proposed.zoom {
            case "target" where hasTarget: result.steps[index].zoom = .target
            case "target": notes.append("Ignored the zoom for \(id): there is no element to zoom on.")
            case "none": result.steps[index].zoom = .none
            default: break
            }
            switch proposed.emphasis {
            case "ripple": result.steps[index].emphasis = .ripple
            case "none": result.steps[index].emphasis = ClickEmphasis.none
            default: break
            }
        }

        // The result must still be a spec a take will accept.
        if (try? result.validate()) == nil {
            return DemoScriptResult(spec: spec, notes: ["The script could not be applied, so nothing changed."], reply: prose)
        }
        return DemoScriptResult(spec: result, notes: notes, reply: prose)
    }

    private static func jsonObject(in reply: String) -> Data? {
        for marker in ["```json", "```JSON", "```"] {
            guard let open = reply.range(of: marker),
                  let close = reply.range(of: "```", range: open.upperBound..<reply.endIndex) else { continue }
            let body = reply[open.upperBound..<close.lowerBound].trimmingCharacters(in: .whitespacesAndNewlines)
            if body.hasPrefix("{") { return Data(body.utf8) }
        }
        guard let start = reply.firstIndex(of: "{") else { return nil }
        var depth = 0, inString = false, escaped = false
        var index = start
        while index < reply.endIndex {
            let c = reply[index]
            if escaped { escaped = false }
            else if c == "\\" { escaped = true }
            else if c == "\"" { inString.toggle() }
            else if !inString {
                if c == "{" { depth += 1 }
                else if c == "}" { depth -= 1; if depth == 0 { return Data(reply[start...index].utf8) } }
            }
            index = reply.index(after: index)
        }
        return nil
    }
}

/// Asks the InnomightLabs agent over A2A, the way `InnomightLabsEditSuggester` does: one durable
/// conversation per demo, so a second request ("shorter, and friendlier") continues the first.
struct InnomightLabsDemoScripter: DemoScripting {
    private let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    func writeScript(for spec: DemoSpec, instruction: String) async throws -> DemoScriptResult {
        let configuration = try AgentSettings.resolved()
        let prompt = DemoScriptPrompt.build(spec: spec, instruction: instruction)
        guard prompt.count <= InnomightLabsEditSuggester.maximumMessageCharacters else {
            throw EditSuggestionError.server(status: 0, detail: "This demo has too many steps to script in one go.")
        }
        let request = try InnomightLabsEditSuggester.request(
            to: configuration.messageEndpoint, secret: configuration.a2aSecret,
            body: InnomightLabsEditSuggester.rpcBody(prompt: prompt, contextID: "aura-demo-\(spec.id.uuidString)")
        )
        let data: Data
        let response: URLResponse
        do { (data, response) = try await session.data(for: request) }
        catch { throw EditSuggestionError.transport(error.localizedDescription) }
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw EditSuggestionError.server(status: http.statusCode, detail: InnomightLabsEditSuggester.detail(in: data))
        }
        return DemoScriptParser.apply(try InnomightLabsEditSuggester.reply(in: data), to: spec)
    }
}
