import AVFoundation
import SwiftUI

struct BrowserDemoView: View {
    @ObservedObject var presenter: BrowserDemoPresenter
    @ObservedObject var installer: BrowserEngineInstaller
    @AppStorage("Aura.browserDemo.forceLoginHandover") private var forceLogin = false
    @AppStorage("Aura.browserDemo.manualResetBeforeTake") private var manualReset = false
    @AppStorage("Aura.browserDemo.narrate") private var narrate = true
    @State private var approvesSideEffects = false
    @State private var newTitle = ""
    @State private var newAddress = ""
    @State private var isNaming = false
    @State private var instruction = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Record a browser demo").font(.title2.bold())
                installerControls
                Divider()
                if let engine = presenter.engine, presenter.isReplaying {
                    BrowserReplayStatusView(engine: engine, stop: presenter.stop)
                } else if let recorder = presenter.recorder {
                    DemonstrationStatusView(
                        recorder: recorder,
                        finish: { Task { await presenter.finishDemonstration() } },
                        cancel: presenter.cancelDemonstration
                    )
                } else {
                    library
                    if let spec = presenter.workingSpec {
                        Divider()
                        SpecEditor(spec: Binding(get: { presenter.workingSpec ?? spec }, set: { presenter.workingSpec = $0 }))
                        saveBar
                        Divider()
                        scriptSection
                        Divider()
                        takeSection(spec)
                    }
                }
                if let error = presenter.errorMessage { Text(error).font(.callout).foregroundStyle(.red) }
                if let error = presenter.engine?.lastError { Text(error).foregroundStyle(.red) }
                if let stepID = presenter.engine?.failedStepID {
                    Text("Step \(stepID) did not work. Re-record the demonstration, or fix that step in the editor, then try again.")
                        .font(.callout)
                }
                if presenter.engine?.state == .finished {
                    Text("Take saved and opened in Aura's editor. Ask the assistant there to polish it.").foregroundStyle(.green)
                }
                Text("You enter credentials yourself, in Chrome. Aura records the steps you take and never what you type into sign-in fields; recording pauses while you sign in.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .padding(20)
        }
        .frame(minWidth: 640, minHeight: 520)
        .onChange(of: presenter.spec) { _, _ in approvesSideEffects = false }
    }

    // MARK: - Library

    @ViewBuilder private var library: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Your demos").font(.headline)
            if presenter.specs.isEmpty {
                Text("Nothing yet. Record a demonstration: do the flow once in Chrome and Aura writes it down.")
                    .foregroundStyle(.secondary)
            }
            ForEach(presenter.specs, id: \.id) { demo in
                HStack {
                    Button {
                        presenter.select(demo)
                    } label: {
                        Label(demo.title, systemImage: presenter.spec?.id == demo.id ? "checkmark.circle.fill" : "circle")
                    }
                    .buttonStyle(.plain)
                    Text("\(demo.steps.count) steps").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button(role: .destructive) { presenter.delete(demo) } label: { Image(systemName: "trash") }
                        .buttonStyle(.borderless).help("Delete this demo and its saved Chrome profile")
                        .disabled(presenter.isBusy)
                }
            }
            if isNaming {
                VStack(alignment: .leading, spacing: 8) {
                    TextField("Name, for example “Build a chatbot”", text: $newTitle)
                    TextField("Where it starts, for example app.example.com", text: $newAddress)
                    Text("Chrome opens here. Click through the flow once, as you want viewers to see it.")
                        .font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Button("Open Chrome and start") {
                            presenter.beginDemonstration(title: newTitle, address: newAddress)
                            isNaming = false; newTitle = ""; newAddress = ""
                        }
                        .disabled(!installer.isReady || newAddress.trimmingCharacters(in: .whitespaces).isEmpty)
                        Button("Cancel") { isNaming = false }
                    }
                }
            } else {
                HStack {
                    Button("Record a new demonstration…") { isNaming = true }.disabled(!installer.isReady || presenter.isBusy)
                    Button("Import spec…", action: presenter.importSpec).disabled(presenter.isBusy)
                }
            }
        }
    }

    private var saveBar: some View {
        HStack {
            Button("Save") { presenter.save() }.disabled(!presenter.hasUnsavedChanges)
            Button("Revert", action: presenter.revert).disabled(!presenter.hasUnsavedChanges)
            if presenter.hasUnsavedChanges { Text("Unsaved changes").font(.caption).foregroundStyle(.orange) }
        }
    }

    // MARK: - Script

    @ViewBuilder private var scriptSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("The words").font(.headline)
            Text("Ask Ila to write the intro, the narration and where to zoom. It only changes wording and emphasis: every action is one you took.")
                .font(.callout).foregroundStyle(.secondary)
            TextField("Tone and length, for example “friendly, for developers, about a minute”", text: $instruction, axis: .vertical)
                .lineLimit(1...3)
            HStack {
                Button(presenter.isWritingScript ? "Writing…" : "Write the script with Ila") {
                    presenter.writeScript(instruction: instruction)
                }
                .disabled(!presenter.isAgentConfigured || presenter.isBusy)
                if presenter.isWritingScript { ProgressView().controlSize(.small) }
            }
            if !presenter.isAgentConfigured {
                Text("Connect your InnomightLabs agent in Agent Settings to have it write the script. You can also type the narration yourself above.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let reply = presenter.scriptReply { Text(reply).font(.callout) }
            ForEach(presenter.scriptNotes, id: \.self) { Text($0).font(.caption).foregroundStyle(.orange) }
        }
    }

    // MARK: - Take

    @ViewBuilder private func takeSection(_ spec: DemoSpec) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Take").font(.headline)
            Toggle("Narrate with a voice", isOn: $narrate)
            if narrate {
                Picker("Voice", selection: $presenter.narrationVoiceIdentifier) {
                    Text("Best available").tag(String?.none)
                    ForEach(SystemSpeechSynthesizer.availableVoices(), id: \.identifier) { voice in
                        Text("\(voice.name)\(Self.qualityLabel(voice))").tag(Optional(voice.identifier))
                    }
                }
                Text("Spoken on this Mac. The take waits for each line, so voice and picture stay together.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Toggle("Always ask me to complete login handovers", isOn: $forceLogin)
            Toggle("Let me reset the site after rehearsal", isOn: $manualReset)
            Text("Rehearsal and recording both perform real actions. Each may create or change data. Use a demo account. Returning to the start URL does not undo those changes.")
                .font(.callout).foregroundStyle(.orange)
            Toggle("I approve running this demo twice", isOn: $approvesSideEffects)
            HStack {
                Button("Rehearse and record") {
                    presenter.start(forceLogin: forceLogin, manualReset: manualReset, narrate: narrate)
                    approvesSideEffects = false
                }
                .disabled(!installer.isReady || !approvesSideEffects || presenter.isBusy)
                if let progress = presenter.narrationProgress {
                    ProgressView(value: Double(progress.done), total: Double(max(progress.total, 1)))
                        .frame(width: 140)
                    Text("Speaking line \(min(progress.done + 1, progress.total)) of \(progress.total)…").font(.caption)
                }
            }
        }
    }

    private static func qualityLabel(_ voice: AVSpeechSynthesisVoice) -> String {
        switch voice.quality {
        case .premium: return " · premium"
        case .enhanced: return " · enhanced"
        default: return ""
        }
    }

    // MARK: - Engine

    @ViewBuilder private var installerControls: some View {
        switch installer.state {
        case .off:
            Button("Enable browser engine…") { installer.beginEnabling() }
        case .awaitingConsent:
            Text("Downloads Node.js and Playwright Core (about 55 MB) from nodejs.org and registry.npmjs.org. Files are pinned and verified. Aura will control a separate Chrome window and profile, never your regular Chrome profile.")
                .font(.callout)
            HStack {
                Button("Agree and download") { installer.acceptConsent() }
                Button("Cancel") { installer.declineConsent() }
            }
        case .installing(let fraction):
            ProgressView("Installing browser engine…", value: fraction)
            Button("Cancel download") { installer.cancelInstall() }
        case .ready:
            HStack {
                Label("Browser engine ready", systemImage: "checkmark.circle")
                Spacer()
                Button("Remove engine") {
                    Task {
                        do { try await installer.uninstall() }
                        catch { presenter.errorMessage = error.localizedDescription }
                    }
                }.disabled(presenter.isBusy)
            }
        case .unavailable(let reason):
            Text(reason).foregroundStyle(.secondary)
            Button("Check again") { installer.refreshAvailability() }
        case .failed(let reason):
            Text(reason).foregroundStyle(.red)
            Button("Retry install") { installer.retry() }
        }
    }
}

// MARK: - The spec editor

/// Edits the words and emphasis of a demo, and the order and presence of its steps. What a step
/// does is not editable here: that is what the user showed, and changing it means showing it again.
private struct SpecEditor: View {
    @Binding var spec: DemoSpec

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("The demo").font(.headline)
            TextField("Title", text: $spec.title)
            TextField("Spoken before the first step", text: optional($spec.intro), axis: .vertical).lineLimit(1...4)
            ForEach(Array(spec.steps.enumerated()), id: \.element.id) { index, step in
                StepRow(
                    number: index + 1, step: $spec.steps[index],
                    canMoveUp: index > 0, canMoveDown: index < spec.steps.count - 1,
                    moveUp: { spec.steps.swapAt(index, index - 1) },
                    moveDown: { spec.steps.swapAt(index, index + 1) },
                    delete: { if spec.steps.count > 1 { spec.steps.remove(at: index) } },
                    canDelete: spec.steps.count > 1
                )
            }
            TextField("Spoken after the last step", text: optional($spec.outro), axis: .vertical).lineLimit(1...4)
        }
    }

    private func optional(_ binding: Binding<String?>) -> Binding<String> {
        Binding(get: { binding.wrappedValue ?? "" }, set: { binding.wrappedValue = $0.isEmpty ? nil : $0 })
    }
}

private struct StepRow: View {
    let number: Int
    @Binding var step: DemoStep
    let canMoveUp: Bool
    let canMoveDown: Bool
    let moveUp: () -> Void
    let moveDown: () -> Void
    let delete: () -> Void
    let canDelete: Bool

    private var isHandover: Bool { if case .handover = step.action { return true } else { return false } }
    private var hasTarget: Bool {
        switch step.action { case .click, .fill: return true; default: return false }
    }
    private var isClick: Bool { if case .click = step.action { return true } else { return false } }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("\(number)").font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(width: 22)
                TextField("What happens", text: $step.intent)
                Button(action: moveUp) { Image(systemName: "chevron.up") }.disabled(!canMoveUp)
                Button(action: moveDown) { Image(systemName: "chevron.down") }.disabled(!canMoveDown)
                Button(role: .destructive, action: delete) { Image(systemName: "trash") }.disabled(!canDelete)
            }
            .buttonStyle(.borderless)
            if isHandover {
                Text("You sign in here. Recording pauses and nothing is spoken.").font(.caption).foregroundStyle(.secondary).padding(.leading, 28)
            } else {
                TextField("What the narrator says", text: Binding(get: { step.narration ?? "" }, set: { step.narration = $0.isEmpty ? nil : $0 }), axis: .vertical)
                    .lineLimit(1...3).padding(.leading, 28)
                HStack(spacing: 16) {
                    if hasTarget {
                        Picker("Zoom", selection: zoomBinding) {
                            Text("No zoom").tag(ZoomChoice.none)
                            Text("Zoom on the element").tag(ZoomChoice.target)
                            if case .region = step.zoom { Text("Custom region").tag(ZoomChoice.region) }
                        }
                        .frame(width: 230)
                    }
                    if isClick {
                        Toggle("Click ripple", isOn: Binding(get: { step.emphasis == .ripple }, set: { step.emphasis = $0 ? .ripple : ClickEmphasis.none }))
                    }
                }
                .padding(.leading, 28).font(.callout)
            }
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.primary.opacity(0.05)))
    }

    private enum ZoomChoice: Hashable { case none, target, region }

    private var zoomBinding: Binding<ZoomChoice> {
        Binding(
            get: {
                switch step.zoom { case .none: return .none; case .target: return .target; case .region: return .region }
            },
            set: { choice in
                switch choice {
                case .none: step.zoom = ZoomHint.none
                case .target: step.zoom = .target
                case .region: break // Only the file can describe one; the picker never creates it.
                }
            }
        )
    }
}

// MARK: - Status while Chrome is in use

private struct DemonstrationStatusView: View {
    @ObservedObject var recorder: DemonstrationRecorder
    let finish: () -> Void
    let cancel: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Chrome is open: do the flow now", systemImage: "record.circle")
                .font(.headline).foregroundStyle(.red)
            Text("Click through it as you want viewers to see it. Aura writes down each step as you go. Closing Chrome finishes the demonstration.")
            Text("Signing in: type your credentials as you normally would. Aura notes that you signed in and records nothing you type there.")
                .font(.callout).foregroundStyle(.secondary)
            if recorder.state == .launching { ProgressView("Opening Chrome…") }
            if recorder.steps.isEmpty {
                Text("No steps yet.").foregroundStyle(.secondary)
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(recorder.steps.enumerated()), id: \.element.id) { index, step in
                        Text("\(index + 1). \(step.intent)").font(.callout)
                    }
                }
            }
            HStack {
                Button("Finish demonstration", action: finish).disabled(recorder.state != .recording || recorder.steps.isEmpty)
                Button("Cancel", role: .cancel, action: cancel)
            }
        }
    }
}

struct BrowserReplayStatusView: View {
    @ObservedObject var engine: ReplayEngine
    let stop: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Aura is controlling its Chrome window", systemImage: "hand.raised.fill")
                .font(.headline)
            switch engine.state {
            case .userControl(let handover):
                Text(handover.phase == .reset ? "Prepare the site for the recorded take, then Resume." : "Your turn: complete the requested action in Chrome, then Resume.")
                Text("Recording is not capturing this handover.").font(.caption)
                if handover.expectationNotMet {
                    Text("The expected page is not ready. Finish in Chrome and try Resume again.")
                        .foregroundStyle(.orange)
                }
                Button("Resume") { engine.resume() }
            case .launching: Text("Launching Chrome…")
            case .calibrating: Text("Calibrating the viewport…")
            case .rehearsing(let step): Text("Rehearsing \(step)…")
            case .preparingTake: Text("Preparing the recorded take…")
            case .recording(let step): Text(step.map { "Recording \($0)…" } ?? "Recording…")
            case .stopping: Text("Stopping and saving…")
            case .idle, .finished, .stopped, .failed: EmptyView()
            }
            Button("Stop (Escape)", action: stop).disabled(engine.state == .stopping)
            Text("Escape outside Aura depends on macOS keyboard-monitoring permission. This Stop button is always available.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}
