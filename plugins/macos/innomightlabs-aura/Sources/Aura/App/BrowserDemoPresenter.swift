import AppKit
import Combine
import SwiftUI
import UniformTypeIdentifiers

/// App-owned so dismissing the menu never cancels a take or loses its Stop control.
///
/// Owns the whole demo workflow: record a demonstration, edit the spec, have the agent write the
/// words, speak them, then take it. Each step is its own method so the view stays a thin layer.
@MainActor
final class BrowserDemoPresenter: NSObject, ObservableObject, NSWindowDelegate {
    let installer = BrowserEngineInstaller()
    @Published private(set) var engine: ReplayEngine?
    @Published private(set) var recorder: DemonstrationRecorder?
    @Published private(set) var specs: [DemoSpec] = []
    /// The saved revision of the selected demo.
    @Published private(set) var spec: DemoSpec?
    /// What the editor shows. Differs from `spec` while there are unsaved changes.
    @Published var workingSpec: DemoSpec?
    @Published var errorMessage: String?
    @Published private(set) var isWritingScript = false
    @Published private(set) var scriptNotes: [String] = []
    @Published private(set) var scriptReply: String?
    @Published private(set) var narrationProgress: (done: Int, total: Int)?
    @Published var narrationVoiceIdentifier: String? = NarrationVoice.identifier {
        didSet { NarrationVoice.identifier = narrationVoiceIdentifier }
    }

    private var window: NSWindow?
    private var observations: Set<AnyCancellable> = []
    private var localEscape: Any?
    private var globalEscape: Any?
    private let controller: RecordingController
    private let store: DemoSpecStore
    private let scripter: any DemoScripting

    init(recorder: RecordingController, scripter: any DemoScripting = InnomightLabsDemoScripter()) {
        self.controller = recorder
        self.scripter = scripter
        store = DemoSpecStore(rootDirectory: FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Aura/DemoSpecs", isDirectory: true))
        super.init()
        installer.objectWillChange.sink { [weak self] _ in self?.objectWillChange.send() }.store(in: &observations)
    }

    var isRecordingDemonstration: Bool { recorder?.isRunning == true }
    var isReplaying: Bool { engine?.isRunning == true }
    /// True while anything holds Chrome, the recorder, or the narration voice.
    var isRunning: Bool { isReplaying || isRecordingDemonstration }
    var isBusy: Bool { isRunning || isWritingScript || narrationProgress != nil }
    var hasUnsavedChanges: Bool { workingSpec != spec }

    // MARK: - Window

    func open() {
        guard FeatureFlags.isBrowserDemoEnabled else { return }
        if let window { window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true); return }
        installer.refreshAvailability()
        refresh()
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 760, height: 720),
                              styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Aura — Browser Demo"
        window.minSize = NSSize(width: 640, height: 520)
        window.level = .floating
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.contentView = NSHostingView(rootView: BrowserDemoView(presenter: self, installer: installer))
        window.center()
        self.window = window
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        guard !isBusy else {
            errorMessage = "Stop the browser demo before closing this window. Any partial recording will be kept."
            return false
        }
        return true
    }

    // MARK: - Saved demos

    func refresh() {
        specs = store.list()
        if let spec, let current = specs.first(where: { $0.id == spec.id }) { select(current) }
        else if spec != nil { select(nil) }
    }

    func select(_ demo: DemoSpec?) {
        guard !isBusy else { return }
        spec = demo
        workingSpec = demo
        scriptNotes = []
        scriptReply = nil
    }

    @discardableResult
    func save() -> Bool {
        guard var draft = workingSpec else { return false }
        do {
            // A cleared line is no line: an empty string would be spoken as nothing.
            for index in draft.steps.indices where draft.steps[index].narration?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == true {
                draft.steps[index].narration = nil
            }
            if draft.intro?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == true { draft.intro = nil }
            if draft.outro?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == true { draft.outro = nil }
            let saved = try store.save(draft)
            spec = saved
            workingSpec = saved
            specs = store.list()
            errorMessage = nil
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func revert() { workingSpec = spec }

    func delete(_ demo: DemoSpec) {
        guard !isBusy else { return }
        do {
            try store.delete(id: demo.id)
            if spec?.id == demo.id { select(nil) }
            specs = store.list()
        } catch { errorMessage = error.localizedDescription }
    }

    func importSpec() {
        guard !isBusy else { return }
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.json]
        panel.allowsMultipleSelection = false
        panel.message = "Choose an aura-demo/v1 spec. Never include credentials."
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            var imported = try store.load(from: url)
            let storedURL = store.directory(for: imported.id).appendingPathComponent("spec.json")
            if FileManager.default.fileExists(atPath: storedURL.path) {
                let previous = try store.load(id: imported.id)
                let alert = NSAlert()
                alert.messageText = "Replace the saved demo spec?"
                alert.informativeText = "Import this file as a new revision of \(previous.title)? The dedicated Chrome profile is preserved. Existing takes keep their original spec."
                alert.addButton(withTitle: "Import new revision")
                alert.addButton(withTitle: "Cancel")
                guard alert.runModal() == .alertFirstButtonReturn else { return }
                imported.revision = previous.revision
            }
            let saved = try store.save(imported)
            specs = store.list()
            select(saved)
            errorMessage = nil
        } catch { errorMessage = error.localizedDescription }
    }

    // MARK: - Demonstrating

    func beginDemonstration(title: String, address: String) {
        guard installer.isReady, !isBusy else { return }
        guard let url = Self.url(from: address) else { errorMessage = DemonstrationError.invalidStartURL.localizedDescription; return }
        guard let host = makeHost() else { return }
        let recorder = DemonstrationRecorder(browser: host)
        self.recorder = recorder
        recorder.objectWillChange.sink { [weak self] in self?.objectWillChange.send() }.store(in: &observations)
        // Closing Chrome is how a demonstration ends, so it finishes the same as the button does.
        recorder.$state.removeDuplicates().filter { $0 == .finishing }.sink { [weak self] _ in
            Task { @MainActor in await self?.finishDemonstration() }
        }.store(in: &observations)

        let id = UUID()
        Task {
            do {
                try await recorder.start(title: title.isEmpty ? "Untitled demo" : title, startURL: url,
                                         profileDirectory: store.profileDirectory(for: id))
                pendingDemonstrationID = id
                errorMessage = nil
            } catch {
                self.recorder = nil
                // Chrome may already have made a profile folder for a demo that will never exist.
                try? store.delete(id: id)
                errorMessage = error.localizedDescription
            }
        }
    }

    private var pendingDemonstrationID: UUID?
    private var isFinishingDemonstration = false

    func finishDemonstration() async {
        // Closing Chrome and pressing Finish both land here; only the first does the work.
        guard let recorder, recorder.state != .idle, !isFinishingDemonstration else { return }
        isFinishingDemonstration = true
        defer { isFinishingDemonstration = false }
        do {
            var demo = try await recorder.finish()
            if let id = pendingDemonstrationID { demo.id = id }
            let saved = try store.save(demo)
            specs = store.list()
            select(saved)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
        pendingDemonstrationID = nil
        self.recorder = nil
    }

    func cancelDemonstration() {
        Task {
            await recorder?.cancel()
            if let id = pendingDemonstrationID { try? store.delete(id: id) }
            pendingDemonstrationID = nil
            recorder = nil
        }
    }

    // MARK: - The agent writes the words

    var isAgentConfigured: Bool { AgentSettings.isConfigured }

    func writeScript(instruction: String) {
        guard let draft = workingSpec, !isBusy else { return }
        isWritingScript = true
        scriptNotes = []
        scriptReply = nil
        Task {
            defer { isWritingScript = false }
            do {
                let result = try await scripter.writeScript(for: draft, instruction: instruction)
                workingSpec = result.spec
                scriptNotes = result.notes
                scriptReply = result.reply.isEmpty ? nil : result.reply
                errorMessage = nil
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    // MARK: - Taking

    func start(forceLogin: Bool, manualReset: Bool, narrate: Bool) {
        guard installer.isReady, !isBusy, workingSpec != nil else { return }
        if hasUnsavedChanges, !save() { return }
        guard let spec else { return }
        Task {
            do {
                var options = ReplayOptions(forceLoginHandover: forceLogin, manualResetBeforeTake: manualReset)
                if narrate { options.narration = try await narration(for: spec) }
                try launchReplay(spec: spec, options: options)
            } catch is CancellationError {
                narrationProgress = nil
            } catch {
                narrationProgress = nil
                errorMessage = error.localizedDescription
            }
        }
    }

    /// Speaks every line before the take starts, so the take can wait for each one. Lines already
    /// spoken for this text and voice come from the cache and cost nothing.
    private func narration(for spec: DemoSpec) async throws -> NarrationTrack? {
        let items = NarrationPlan.items(for: spec)
        guard !items.isEmpty else { return nil }
        narrationProgress = (0, items.count)
        defer { narrationProgress = nil }
        let total = items.count
        let voice = try NarrationVoice.resolve()
        return try await NarrationRenderer.render(
            items, voice: NarrationVoice.reference, voiceID: voice.cacheID, using: voice.synthesizer,
            cacheDirectory: store.directory(for: spec.id).appendingPathComponent("narration-cache", isDirectory: true)
        ) { done in
            Task { @MainActor [weak self] in self?.narrationProgress = (done, total) }
        }
    }

    private func launchReplay(spec: DemoSpec, options: ReplayOptions) throws {
        guard let host = makeHost() else { return }
        let engine = ReplayEngine(browser: host, recordingController: controller)
        self.engine = engine
        engine.objectWillChange.sink { [weak self, weak engine] in
            Task { @MainActor in
                self?.objectWillChange.send()
                if engine?.isRunning == false { self?.removeEscapeMonitors() }
            }
        }.store(in: &observations)
        do {
            try engine.start(spec: spec, profileDirectory: store.profileDirectory(for: spec.id), options: options)
            errorMessage = nil
            installEscapeMonitors()
        } catch {
            self.engine = nil
            throw error
        }
    }

    func stop() {
        Task { await stopAll() }
    }

    /// Ends whatever is using Chrome and waits until it has finished, so quitting never abandons a
    /// take whose media is still being written.
    func stopAll() async {
        if isRecordingDemonstration {
            await recorder?.cancel()
            if let id = pendingDemonstrationID { try? store.delete(id: id) }
            pendingDemonstrationID = nil
            recorder = nil
        }
        await engine?.stop()
        removeEscapeMonitors()
    }

    // MARK: - Helpers

    private func makeHost() -> PlaywrightBrowserHost? {
        guard let script = Bundle.main.url(forResource: "aura-browser-host", withExtension: "mjs") else {
            errorMessage = "Aura's browser host resource is missing. Rebuild the app before recording."
            return nil
        }
        return PlaywrightBrowserHost(nodeURL: installer.nodeURL, scriptURL: script, workingDirectory: installer.workingDirectory)
    }

    /// What people type: a bare host name is taken to mean https.
    static func url(from address: String) -> URL? {
        var text = address.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }
        if !text.contains("://") { text = "https://" + text }
        guard let url = URL(string: text), (try? DemoSpec.origin(of: url)) != nil else { return nil }
        return url
    }

    private func installEscapeMonitors() {
        removeEscapeMonitors()
        localEscape = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            if event.keyCode == 53 {
                Task { @MainActor in self?.stop() }
                return nil
            }
            return event
        }
        // macOS may require Input Monitoring for keys in other apps; the floating Stop button
        // remains available regardless. No extra permission is requested just to show this UI.
        globalEscape = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
            if event.keyCode == 53 { Task { @MainActor in self?.stop() } }
        }
    }

    private func removeEscapeMonitors() {
        if let localEscape { NSEvent.removeMonitor(localEscape) }
        if let globalEscape { NSEvent.removeMonitor(globalEscape) }
        localEscape = nil; globalEscape = nil
    }
}
