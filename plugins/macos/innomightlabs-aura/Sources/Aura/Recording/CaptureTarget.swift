import ScreenCaptureKit

/// `SCDisplay`/`SCWindow`/`SCRunningApplication` are immutable snapshot objects from
/// `SCShareableContent`, safe to hand across the main actor -> capture-queue boundary.
enum CaptureTarget: Hashable, @unchecked Sendable {
    case display(SCDisplay)
    case window(SCWindow)
    case app(SCRunningApplication, on: SCDisplay)

    var displayName: String {
        switch self {
        case .display(let display):
            return "Display \(display.displayID)"
        case .window(let window):
            return window.title ?? window.owningApplication?.applicationName ?? "Window \(window.windowID)"
        case .app(let app, _):
            return app.applicationName
        }
    }

    /// Native pixel dimensions of this target, used both for `SCStreamConfiguration`
    /// and for the `screen.mov` `AVAssetWriterInput`'s output settings.
    var pixelSize: CGSize {
        let filter = contentFilter()
        let scale = CGFloat(filter.pointPixelScale)
        let rect = filter.contentRect
        return CGSize(width: max(2, rect.width * scale), height: max(2, rect.height * scale))
    }

    func contentFilter() -> SCContentFilter {
        switch self {
        case .display(let display):
            return SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
        case .window(let window):
            return SCContentFilter(desktopIndependentWindow: window)
        case .app(let app, let display):
            return SCContentFilter(display: display, including: [app], exceptingWindows: [])
        }
    }

    /// Best-name-match for `name` among `targets`, or `nil` if none is close enough.
    /// Delegates to `NameMatcher` so the matching algorithm itself stays unit-testable
    /// without needing real `SCDisplay`/`SCWindow`/`SCRunningApplication` fixtures.
    static func bestMatch(for name: String, among targets: [CaptureTarget]) -> CaptureTarget? {
        NameMatcher.bestMatch(for: name, among: targets.map { ($0.displayName, $0) })
    }
}

/// Pure "closest name" matching, shared by picker-preference restoration and voice-driven
/// target resolution. Exact case-insensitive match wins; otherwise a substring match
/// (either direction) closest in length to the query; otherwise `nil`.
enum NameMatcher {
    static func bestMatch<T>(for name: String, among candidates: [(name: String, value: T)]) -> T? {
        let query = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty, !candidates.isEmpty else { return nil }
        let lowerQuery = query.lowercased()

        if let exact = candidates.first(where: { $0.name.lowercased() == lowerQuery }) {
            return exact.value
        }

        let substringMatches = candidates.filter {
            let lowerName = $0.name.lowercased()
            return lowerName.contains(lowerQuery) || lowerQuery.contains(lowerName)
        }
        return substringMatches.min { abs($0.name.count - query.count) < abs($1.name.count - query.count) }?.value
    }
}
