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
}
