import Foundation

struct WindowSize: Codable, Equatable, Sendable {
    var width: Int
    var height: Int
}

struct BrowserRect: Codable, Equatable, Sendable {
    var x: Double
    var y: Double
    var width: Double
    var height: Double
}

struct ElementTarget: Codable, Equatable, Sendable {
    var candidates: [LocatorCandidate]
    /// Display-only; never used to resolve ambiguity or choose a click position.
    var hintRect: BrowserRect? = nil
}

struct LocatorCandidate: Codable, Equatable, Sendable {
    var testId: String? = nil
    var role: String? = nil
    var name: String? = nil
    var text: String? = nil
    var css: String? = nil
}

struct Expectation: Codable, Equatable, Sendable {
    var url: String? = nil
    var visible: LocatorCandidate? = nil
}

struct ScrollPosition: Codable, Equatable, Sendable {
    var x: Double
    var y: Double
    /// Absent in older specs: scroll the document viewport.
    var target: ElementTarget? = nil
}

enum HandoverReason: String, Codable, Sendable { case login, manual }
enum ClickEmphasis: String, Codable, Sendable { case none, ripple }

enum ZoomHint: Equatable, Sendable, Codable {
    case none, target, region(BrowserRect)

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if let value = try? c.decode(String.self) {
            switch value {
            case "none": self = .none
            case "target": self = .target
            default: throw DemoSpecError.invalid("Unknown zoom hint")
            }
        } else {
            self = .region(try c.decode(BrowserRect.self))
        }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .none: try c.encode("none")
        case .target: try c.encode("target")
        case .region(let rect): try c.encode(rect)
        }
    }
}

enum InputValue: Equatable, Sendable, Codable {
    case literal(String), parameter(String)
    private enum Keys: String, CodingKey { case literal, parameter }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        guard c.contains(.literal) != c.contains(.parameter) else {
            throw DemoSpecError.invalid("Input needs exactly one literal or parameter")
        }
        if c.contains(.literal) { self = .literal(try c.decode(String.self, forKey: .literal)) }
        else { self = .parameter(try c.decode(String.self, forKey: .parameter)) }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: Keys.self)
        switch self {
        case .literal(let value): try c.encode(value, forKey: .literal)
        case .parameter(let name): try c.encode(name, forKey: .parameter)
        }
    }

    func resolved(parameters: [String: String]) throws -> InputValue {
        switch self {
        case .literal: return self
        case .parameter(let name):
            guard let value = parameters[name] else { throw DemoSpecError.invalid("Missing input parameter") }
            return .literal(value)
        }
    }
}

enum DemoAction: Equatable, Sendable, Codable {
    case goto(URL)
    case click(ElementTarget)
    case fill(ElementTarget, value: InputValue)
    case press(key: String)
    case scroll(to: ScrollPosition)
    case wait(seconds: TimeInterval)
    case handover(reason: HandoverReason, doneWhen: Expectation?)

    private enum Keys: String, CodingKey { case action, url, target, value, key, to, seconds, reason, doneWhen }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        switch try c.decode(String.self, forKey: .action) {
        case "goto": self = .goto(try c.decode(URL.self, forKey: .url))
        case "click": self = .click(try c.decode(ElementTarget.self, forKey: .target))
        case "fill": self = .fill(try c.decode(ElementTarget.self, forKey: .target), value: try c.decode(InputValue.self, forKey: .value))
        case "press": self = .press(key: try c.decode(String.self, forKey: .key))
        case "scroll": self = .scroll(to: try c.decode(ScrollPosition.self, forKey: .to))
        case "wait": self = .wait(seconds: try c.decode(Double.self, forKey: .seconds))
        case "handover": self = .handover(reason: try c.decode(HandoverReason.self, forKey: .reason), doneWhen: try c.decodeIfPresent(Expectation.self, forKey: .doneWhen))
        default: throw DemoSpecError.invalid("Unknown browser action")
        }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: Keys.self)
        switch self {
        case .goto(let url): try c.encode("goto", forKey: .action); try c.encode(url, forKey: .url)
        case .click(let target): try c.encode("click", forKey: .action); try c.encode(target, forKey: .target)
        case .fill(let target, let value):
            try c.encode("fill", forKey: .action); try c.encode(target, forKey: .target); try c.encode(value, forKey: .value)
        case .press(let key): try c.encode("press", forKey: .action); try c.encode(key, forKey: .key)
        case .scroll(let to): try c.encode("scroll", forKey: .action); try c.encode(to, forKey: .to)
        case .wait(let seconds): try c.encode("wait", forKey: .action); try c.encode(seconds, forKey: .seconds)
        case .handover(let reason, let doneWhen):
            try c.encode("handover", forKey: .action); try c.encode(reason, forKey: .reason); try c.encodeIfPresent(doneWhen, forKey: .doneWhen)
        }
    }

    func resolved(parameters: [String: String]) throws -> DemoAction {
        if case .fill(let target, let value) = self { return .fill(target, value: try value.resolved(parameters: parameters)) }
        return self
    }
}

struct DemoStep: Codable, Equatable, Identifiable, Sendable {
    var id: String
    var action: DemoAction
    var intent: String
    var expect: Expectation? = nil
    var narration: String? = nil
    var zoom: ZoomHint = .none
    var emphasis: ClickEmphasis = .none
    private enum Keys: String, CodingKey { case id, intent, expect, narration, zoom, emphasis }

    init(id: String, action: DemoAction, intent: String, expect: Expectation? = nil,
         narration: String? = nil, zoom: ZoomHint = .none, emphasis: ClickEmphasis = .none) {
        self.id = id; self.action = action; self.intent = intent; self.expect = expect
        self.narration = narration; self.zoom = zoom; self.emphasis = emphasis
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        id = try c.decode(String.self, forKey: .id)
        action = try DemoAction(from: decoder)
        intent = try c.decode(String.self, forKey: .intent)
        expect = try c.decodeIfPresent(Expectation.self, forKey: .expect)
        narration = try c.decodeIfPresent(String.self, forKey: .narration)
        zoom = try c.decodeIfPresent(ZoomHint.self, forKey: .zoom) ?? .none
        emphasis = try c.decodeIfPresent(ClickEmphasis.self, forKey: .emphasis) ?? .none
    }

    func encode(to encoder: Encoder) throws {
        try action.encode(to: encoder)
        var c = encoder.container(keyedBy: Keys.self)
        try c.encode(id, forKey: .id); try c.encode(intent, forKey: .intent)
        try c.encodeIfPresent(expect, forKey: .expect); try c.encodeIfPresent(narration, forKey: .narration)
        try c.encode(zoom, forKey: .zoom); try c.encode(emphasis, forKey: .emphasis)
    }
}

enum DemoSpecError: Error, LocalizedError, Equatable {
    case invalid(String)
    var errorDescription: String? { if case .invalid(let reason) = self { return reason }; return nil }
}

struct DemoSpec: Codable, Equatable, Sendable {
    static let format = "aura-demo/v1"
    static let maximumBytes = 2 * 1024 * 1024
    var id: UUID
    var revision: Int
    var title: String
    var startURL: URL
    var allowedOrigins: [String]
    var window: WindowSize
    var parameters: [String: String]
    var intro: String? = nil
    var outro: String? = nil
    var steps: [DemoStep]

    private enum Keys: String, CodingKey { case format, id, revision, title, startURL, allowedOrigins, window, parameters, intro, outro, steps }

    init(id: UUID = UUID(), revision: Int = 0, title: String, startURL: URL, allowedOrigins: [String],
         window: WindowSize, parameters: [String: String] = [:], intro: String? = nil, outro: String? = nil, steps: [DemoStep]) {
        self.id = id; self.revision = revision; self.title = title; self.startURL = startURL
        self.allowedOrigins = allowedOrigins; self.window = window; self.parameters = parameters
        self.intro = intro; self.outro = outro; self.steps = steps
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        guard try c.decode(String.self, forKey: .format) == Self.format else { throw DemoSpecError.invalid("Unsupported demo format") }
        id = try c.decode(UUID.self, forKey: .id); revision = try c.decode(Int.self, forKey: .revision)
        title = try c.decode(String.self, forKey: .title); startURL = try c.decode(URL.self, forKey: .startURL)
        allowedOrigins = try c.decode([String].self, forKey: .allowedOrigins); window = try c.decode(WindowSize.self, forKey: .window)
        parameters = try c.decodeIfPresent([String: String].self, forKey: .parameters) ?? [:]
        intro = try c.decodeIfPresent(String.self, forKey: .intro); outro = try c.decodeIfPresent(String.self, forKey: .outro)
        steps = try c.decode([DemoStep].self, forKey: .steps)
        try validate()
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: Keys.self)
        try c.encode(Self.format, forKey: .format); try c.encode(id, forKey: .id); try c.encode(revision, forKey: .revision)
        try c.encode(title, forKey: .title); try c.encode(startURL, forKey: .startURL)
        try c.encode(allowedOrigins, forKey: .allowedOrigins); try c.encode(window, forKey: .window)
        try c.encode(parameters, forKey: .parameters); try c.encodeIfPresent(intro, forKey: .intro)
        try c.encodeIfPresent(outro, forKey: .outro); try c.encode(steps, forKey: .steps)
    }

    static func origin(of url: URL) throws -> String {
        guard url.absoluteString.utf8.count <= 8192,
              let c = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let scheme = c.scheme?.lowercased(), ["http", "https"].contains(scheme),
              let host = c.host?.lowercased(), !host.isEmpty, c.user == nil, c.password == nil,
              c.port == nil || (1...65535).contains(c.port!) else { throw DemoSpecError.invalid("Browser URLs must be HTTP(S) without credentials") }
        let port = c.port
        return "\(scheme)://\(host)" + ((port == nil || port == (scheme == "https" ? 443 : 80)) ? "" : ":\(port!)")
    }

    func validate() throws {
        func require(_ condition: Bool, _ message: String) throws { if !condition { throw DemoSpecError.invalid(message) } }
        func string(_ value: String, _ limit: Int = 8192) throws { try require(value.utf8.count <= limit, "Demo text exceeds size limit") }
        func rect(_ r: BrowserRect) throws {
            try require([r.x, r.y, r.width, r.height].allSatisfy(\.isFinite) && r.width > 0 && r.height > 0, "Invalid target rectangle")
        }
        func candidate(_ c: LocatorCandidate) throws {
            let kinds = [c.testId, c.role, c.text, c.css].compactMap { $0 }
            try require(kinds.count == 1 && !(kinds.first?.isEmpty ?? true) && (c.role == nil ? c.name == nil : c.name?.isEmpty == false), "Invalid locator candidate")
            for s in kinds + [c.name].compactMap({ $0 }) { try string(s, 2048) }
            if let css = c.css { try require(!css.contains(">>>") && !css.lowercased().contains("iframe") && !css.lowercased().contains("frame"), "Frames are unsupported") }
        }
        func target(_ t: ElementTarget) throws {
            try require((1...16).contains(t.candidates.count), "Invalid candidate count")
            try t.candidates.forEach(candidate); if let r = t.hintRect { try rect(r) }
        }
        let origins = try allowedOrigins.map { raw -> String in
            guard raw.utf8.count <= 2048, let url = URL(string: raw), let c = URLComponents(string: raw),
                  c.path.isEmpty || c.path == "/", c.query == nil, c.fragment == nil else { throw DemoSpecError.invalid("Expected an origin, not a URL path") }
            return try Self.origin(of: url)
        }
        func destination(_ url: URL) throws { try require(origins.contains(Self.origin(of: url)), "URL is outside allowed origins") }
        func expectation(_ e: Expectation) throws {
            try require(e.url != nil || e.visible != nil, "Empty expectation")
            if let url = e.url {
                try string(url, 8192)
                if url.hasPrefix("/") { try require(!url.hasPrefix("//"), "Invalid relative expectation URL") }
                else if let absolute = URL(string: url) { try destination(absolute) }
                else { throw DemoSpecError.invalid("Invalid expectation URL") }
            }
            if let visible = e.visible { try candidate(visible) }
        }
        try require(revision >= 0 && revision < Int.max, "Invalid revision")
        try require(!title.isEmpty, "Demo title is empty"); try string(title)
        try require((1...64).contains(origins.count) && Set(origins).count == origins.count, "Invalid allowed origins")
        try destination(startURL)
        try require((320...7680).contains(window.width) && (240...4320).contains(window.height), "Invalid browser window size")
        try require((1...1000).contains(steps.count) && Set(steps.map(\.id)).count == steps.count, "Invalid or duplicate demo steps")
        try require(parameters.count <= 128, "Too many parameters")
        for (key, value) in parameters { try require(!key.isEmpty, "Empty parameter name"); try string(key, 128); try string(value, 16384) }
        for text in [intro, outro].compactMap({ $0 }) { try string(text) }
        for step in steps {
            try require(!step.id.isEmpty, "Empty step id"); try string(step.id, 128); try string(step.intent)
            if let text = step.narration { try string(text) }
            if let e = step.expect { try expectation(e) }
            if case .region(let r) = step.zoom {
                try rect(r); try require(r.x >= 0 && r.y >= 0 && r.x + r.width <= 1 && r.y + r.height <= 1, "Zoom region must be normalized")
            }
            switch step.action {
            case .goto(let url): try destination(url)
            case .click(let t): try target(t)
            case .fill(let t, let value):
                try target(t)
                switch try value.resolved(parameters: parameters) { case .literal(let s): try string(s, 16384); case .parameter: break }
            case .press(let key):
                let pattern = #"^(?:(?:ControlOrMeta|Control|Meta|Alt|Shift)\+)*(?:Enter|Escape|Tab|Backspace|Delete|ArrowUp|ArrowDown|ArrowLeft|ArrowRight|Home|End|PageUp|PageDown|Space)$"#
                try require(key.utf8.count <= 128 && key.range(of: pattern, options: .regularExpression) != nil, "Invalid or text-entry key; use fill for non-sensitive text")
            case .scroll(let p):
                            try require(p.x.isFinite && p.y.isFinite && abs(p.x) <= 10_000_000 && abs(p.y) <= 10_000_000, "Invalid scroll position")
                            if let t = p.target { try target(t) }
            case .wait(let seconds): try require(seconds.isFinite && (0...120).contains(seconds), "Invalid wait duration")
            case .handover(_, let doneWhen): if let e = doneWhen { try expectation(e) }
            }
        }
    }
}
