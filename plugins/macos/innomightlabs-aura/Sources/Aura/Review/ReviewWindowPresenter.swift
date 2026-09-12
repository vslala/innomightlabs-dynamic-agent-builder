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
        let keyMonitor: Any?
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
            observer: observer,
            keyMonitor: Self.installKeyMonitor(window: window, viewModel: viewModel)
        )
        presented[folder.id]?.controller.showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func dismiss(_ id: String) {
        guard let entry = presented.removeValue(forKey: id) else { return }
        NotificationCenter.default.removeObserver(entry.observer)
        if let monitor = entry.keyMonitor {
            NSEvent.removeMonitor(monitor)
        }
        entry.viewModel.close()
        entry.controller.window?.contentView = nil
    }

    /// One local key monitor for the whole window, consulting `ReviewKeyCommand`.
    ///
    /// Preferred over `.keyboardShortcut` on buttons, which this window cannot host well: it
    /// has no `commands` scene to put a menu in, a shortcut on a conditionally-shown button
    /// does not exist while that button is hidden, and a window-wide unmodified shortcut is
    /// resolved ahead of the field editor — so the agent panel's text field could not reliably
    /// receive a space.
    ///
    /// Scoped to this window, and it asks the first responder whether a text field is editing
    /// before treating a bare keystroke as a command.
    private static func installKeyMonitor(window: NSWindow, viewModel: ReviewViewModel) -> Any? {
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            guard event.window === window else { return event }

            let focus: ReviewKeyCommand.Focus = Self.isEditingText(in: window) ? .textInput : .timeline
            var modifiers: ReviewKeyCommand.Modifiers = []
            if event.modifierFlags.contains(.command) { modifiers.insert(.command) }
            if event.modifierFlags.contains(.shift) { modifiers.insert(.shift) }
            if event.modifierFlags.contains(.option) { modifiers.insert(.option) }
            if event.modifierFlags.contains(.control) { modifiers.insert(.control) }

            guard let command = ReviewKeyCommand.resolve(
                characters: (event.charactersIgnoringModifiers ?? "").lowercased(),
                keyCode: event.keyCode,
                modifiers: modifiers,
                focus: focus
            ) else { return event }

            // Unhandled commands fall through, so a keystroke is never silently eaten.
            return MainActor.assumeIsolated { viewModel.perform(command) } ? nil : event
        }
    }

    private static func isEditingText(in window: NSWindow) -> Bool {
        guard let responder = window.firstResponder else { return false }
        if let textView = responder as? NSTextView { return textView.isEditable }
        return responder is NSTextField
    }
}
