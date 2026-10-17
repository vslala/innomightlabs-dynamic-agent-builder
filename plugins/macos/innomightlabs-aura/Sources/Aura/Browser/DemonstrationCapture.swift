import Foundation

/// Turns what the host reports of a demonstration into the steps of a spec.
///
/// Pure and in order: the same events always make the same steps, so the rules below are tested
/// without a browser. The host has already refused credential values; what this decides is shape.
///
/// - Typing into a field is one step with the final text, not one per keystroke.
/// - A navigation that follows an action is that action's result, so replay can wait for it.
/// - Signing in is a handover, never a recording of credentials. It starts when the user reaches for
///   a credential field, or leaves for another origin (an identity provider). Redirects stay inside
///   that handover until the next non-sensitive interaction on an approved page.
struct DemonstrationCapture: Equatable, Sendable {
    private(set) var steps: [DemoStep] = []

    private let allowedOrigins: Set<String>
    private var handoverIsOpen = false
    private var hasUserInteraction = false
    private var handoverCanFinish = false
    private var lastClickNavigated = false
    private var nextNumber = 1

    init(allowedOrigins: [String]) {
        self.allowedOrigins = Set(allowedOrigins)
    }

    // MARK: - Interactions

    mutating func receive(_ interaction: CapturedInteraction) {
        hasUserInteraction = true
        if handoverIsOpen {
            if case .sensitiveInput = interaction {
                openHandover()
                return
            }
            // A return navigation alone may only be another login page. Keep collecting redirects;
            // the first non-sensitive interaction after it belongs to the demo, not the handover.
            guard handoverCanFinish else { return }
            if case .click(let target, _) = interaction,
               case .handover(_, nil) = steps.last?.action {
                steps[steps.count - 1].action = .handover(reason: .login, doneWhen: Expectation(visible: target.candidates.first))
            }
            handoverIsOpen = false
        }
        switch interaction {
        case .sensitiveInput:
            openHandover(foldingClick: lastClickNavigated)
        case .click(let target, _):
            // A click ripples by default: it is the moment the viewer is meant to notice.
            append(.click(target), intent: "Click \(Self.name(of: target))", emphasis: .ripple)
        case .input(let target, let value):
            if let last = steps.last, case .fill(let previous, _) = last.action, previous.candidates == target.candidates {
                steps[steps.count - 1].action = .fill(target, value: .literal(value))
            } else {
                append(.fill(target, value: .literal(value)), intent: "Fill in \(Self.name(of: target))")
            }
        case .press(let key):

            append(.press(key: key), intent: "Press \(key)")
        case .scroll(let position):
            let intent = position.y >= lastScrollY(for: position.target) ? "Scroll down" : "Scroll up"
            if let last = steps.last, case .scroll(let previous) = last.action,
                           previous.target?.candidates == position.target?.candidates {
                steps[steps.count - 1].action = .scroll(to: position)
                steps[steps.count - 1].intent = intent
            } else {
                append(.scroll(to: position), intent: intent)
            }
        }
        lastClickNavigated = false
    }

    mutating func navigated(to url: URL, clean: Bool) {
        guard let origin = try? DemoSpec.origin(of: url) else { return }

        guard allowedOrigins.contains(origin) else {
            // Another origin is an identity provider or a link out. The user is on their own there.
            openHandover(foldingClick: true)
            return
        }

        if handoverIsOpen {
            handoverCanFinish = true
            steps[steps.count - 1].action = .handover(reason: .login, doneWhen: clean ? Expectation(url: Self.path(of: url)) : nil)
            return
        }
        // Aura opens the start page itself, before the user does anything. Wherever that lands, even
        // after a redirect to a sign-in page, it is where the demonstration begins.
        guard hasUserInteraction else { return }

        if let last = steps.last, Self.canExpectNavigation(last.action) {
            // The latest destination wins, so a redirect chain ends on the page the user saw.
            steps[steps.count - 1].expect = clean ? Expectation(url: Self.path(of: url)) : nil
            if case .click = last.action { lastClickNavigated = true }
        } else {
            append(.goto(url), intent: "Go to \(Self.path(of: url))")
        }
    }

    /// The latest approved destination completes a sign-in even if the user stops before interacting
    /// there. Without one, replay waits until the user says they are done.
    func finish() -> [DemoStep] { steps }

    // MARK: - Helpers

    private func lastScrollY(for target: ElementTarget?) -> Double {
        for step in steps.reversed() {
            if case .scroll(let position) = step.action,
               position.target?.candidates == target?.candidates { return position.y }
        }
        return 0
    }

    private mutating func append(_ action: DemoAction, intent: String, emphasis: ClickEmphasis = .none) {
        steps.append(DemoStep(id: "s\(nextNumber)", action: action, intent: intent, emphasis: emphasis))
        nextNumber += 1
    }

    private mutating func openHandover(foldingClick: Bool = false) {
        // Replay must grant user control before the click that leaves for an identity provider.
        // Reuse an adjacent handover too: an intermediate login page is not a completion checkpoint.
        if !handoverIsOpen, foldingClick, case .click = steps.last?.action {
            steps.removeLast()
            nextNumber -= 1
        }
        if case .handover = steps.last?.action {
            steps[steps.count - 1].action = .handover(reason: .login, doneWhen: nil)
        } else {
            append(.handover(reason: .login, doneWhen: nil), intent: "Sign in yourself: Aura never types credentials")
        }
        handoverIsOpen = true
        handoverCanFinish = false
        lastClickNavigated = false
    }

    private static func canExpectNavigation(_ action: DemoAction) -> Bool {
        switch action {
        case .click, .fill, .press, .goto: return true
        case .scroll, .wait, .handover: return false
        }
    }

    private static func path(of url: URL) -> String { url.path.isEmpty ? "/" : url.path }

    /// What the user would call it: the accessible name, else the visible text, else the test id.
    static func name(of target: ElementTarget) -> String {
        for candidate in target.candidates {
            if let name = candidate.name ?? candidate.text ?? candidate.testId { return "“\(name)”" }
        }
        return "the element"
    }
}
