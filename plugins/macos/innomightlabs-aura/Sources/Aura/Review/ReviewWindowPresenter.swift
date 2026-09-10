import AppKit
import SwiftUI

/// Opens and owns review windows.
///
/// AppKit rather than a SwiftUI `WindowGroup` for two reasons specific to a menu-bar app.
/// The trigger has to work: `MenuBarExtra`'s content view only exists while the menu is
/// open, and `stop()` finishes asynchronously *after* clicking Stop has dismissed it, so an
/// `onChange` living in that view is never alive at the moment the session completes.
/// And teardown has to be deterministic: `close()` must run to remove the player's periodic
/// time observer and flush `edit.json`, which is why this owns the view model and tears it
/// down on `willClose` rather than trusting `onDisappear` to fire for a hosted view.
@MainActor
final class ReviewWindowPresenter {
    private struct Presented {
        let controller: NSWindowController
        let viewModel: ReviewViewModel
        let observer: NSObjectProtocol
    }

    /// Keyed by session id, so asking twice for the same recording focuses the open window
    /// instead of building a second composition over the same files.
    private var presented: [String: Presented] = [:]

    func open(_ folder: SessionFolder) {
        if let existing = presented[folder.id] {
            existing.controller.showWindow(nil)
            existing.controller.window?.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        let viewModel = ReviewViewModel(folder: folder)
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1280, height: 800),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Aura — \(folder.id)"
        window.contentView = NSHostingView(rootView: ReviewWindowView(viewModel: viewModel))
        window.isReleasedWhenClosed = false
        window.center()

        let observer = NotificationCenter.default.addObserver(
            forName: NSWindow.willCloseNotification,
            object: window,
            queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated {
                self?.dismiss(folder.id)
            }
        }

        presented[folder.id] = Presented(
            controller: NSWindowController(window: window),
            viewModel: viewModel,
            observer: observer
        )
        presented[folder.id]?.controller.showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func dismiss(_ id: String) {
        guard let entry = presented.removeValue(forKey: id) else { return }
        NotificationCenter.default.removeObserver(entry.observer)
        entry.viewModel.close()
        entry.controller.window?.contentView = nil
    }
}
