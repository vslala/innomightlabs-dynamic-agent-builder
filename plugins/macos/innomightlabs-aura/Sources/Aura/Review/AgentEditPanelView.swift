import SwiftUI

/// Where the user asks for an edit in words — typed, or dictated into the mic.
///
/// The agent never edits directly: it proposes operations, they appear here, and accepting one
/// runs it through the same `EditDocumentStore.apply` a drag does. So an AI edit is reviewable
/// before it lands and undoable after.
struct AgentEditPanelView: View {
    @ObservedObject var viewModel: ReviewViewModel
    @StateObject private var voice = VoiceInstructionRecorder()

    @State private var instruction: String = ""
    @State private var showingSettings = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Label("Ask Aura", systemImage: "sparkles")
                    .font(.headline)
                Spacer()
                Button {
                    showingSettings = true
                } label: {
                    Image(systemName: "gearshape")
                }
                .buttonStyle(.borderless)
                .help("Agent settings")
            }

            if viewModel.isAgentConfigured {
                composer
                statusLine
                suggestionList
            } else {
                notConfigured
            }
        }
        .padding(10)
        .sheet(isPresented: $showingSettings) {
            AgentSettingsView()
        }
    }

    private var composer: some View {
        HStack(spacing: 6) {
            TextField(
                "e.g. cut the part where I stumble, and hide the camera while the terminal is up",
                text: $instruction,
                axis: .vertical
            )
            .lineLimit(1...3)
            .textFieldStyle(.roundedBorder)
            .onSubmit(submit)
            .disabled(viewModel.isAwaitingAgent)

            micButton

            Button {
                submit()
            } label: {
                Image(systemName: "arrow.up.circle.fill")
            }
            .buttonStyle(.borderless)
            .disabled(instruction.trimmingCharacters(in: .whitespaces).isEmpty || viewModel.isAwaitingAgent)
            .help("Ask for these edits")
        }
    }

    /// Press and hold to dictate, matching how push-to-talk works elsewhere in the app.
    private var micButton: some View {
        Button {
            // Handled by the long-press gesture below; a plain click starts and stops.
            toggleDictation()
        } label: {
            Image(systemName: voice.state == .listening ? "mic.fill" : "mic")
                .foregroundStyle(voice.state == .listening ? .red : .primary)
        }
        .buttonStyle(.borderless)
        .disabled(voice.state == .transcribing || viewModel.isAwaitingAgent)
        .help(voice.state == .listening ? "Stop dictating" : "Dictate an instruction")
        .overlay(alignment: .bottom) {
            if voice.state == .transcribing {
                ProgressView().controlSize(.small).offset(y: 14)
            }
        }
    }

    @ViewBuilder
    private var statusLine: some View {
        switch viewModel.agentState {
        case .idle:
            if case .failed(let reason) = voice.state {
                Text(reason)
                    .font(.caption2)
                    .foregroundStyle(.red)
            } else if voice.state == .listening {
                Text("Listening… click the mic again when you're done.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

        case .thinking:
            HStack(spacing: 6) {
                ProgressView().controlSize(.small)
                Text("Thinking…").font(.caption)
            }

        case .replied(let reply):
            if !reply.isEmpty {
                Text(reply)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

        case .failed(let reason):
            Text(reason)
                .font(.caption2)
                .foregroundStyle(.red)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder
    private var suggestionList: some View {
        if !viewModel.suggestions.isEmpty {
            HStack {
                Text("\(viewModel.suggestions.count) proposed")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Apply All") { viewModel.acceptAllSuggestions() }
                    .font(.caption)
                Button("Dismiss") { viewModel.clearAgentReply() }
                    .font(.caption)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(viewModel.suggestions) { suggestion in
                        SuggestionRow(
                            suggestion: suggestion,
                            onAccept: { viewModel.accept(suggestion) },
                            onReject: { viewModel.reject(suggestion) }
                        )
                    }
                }
            }
            .frame(maxHeight: 150)
        }
    }

    private var notConfigured: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Connect your InnomightLabs agent to edit by asking.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Button("Agent Settings…") { showingSettings = true }
                .font(.caption)
        }
    }

    private func submit() {
        let text = instruction.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        viewModel.requestSuggestions(instruction: text)
        instruction = ""
    }

    private func toggleDictation() {
        if voice.state == .listening {
            Task {
                if let text = await voice.finish() {
                    instruction = instruction.isEmpty ? text : instruction + " " + text
                }
            }
        } else {
            voice.start()
        }
    }
}

private struct SuggestionRow: View {
    let suggestion: EditSuggestion
    let onAccept: () -> Void
    let onReject: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            VStack(alignment: .leading, spacing: 1) {
                Text(EditOperationDescription.summary(suggestion.operation))
                    .font(.system(size: 11, weight: .medium))
                if let rationale = suggestion.rationale {
                    Text(rationale)
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Button(action: onAccept) { Image(systemName: "checkmark") }
                .buttonStyle(.borderless)
                .help("Apply this edit")
            Button(action: onReject) { Image(systemName: "xmark") }
                .buttonStyle(.borderless)
                .help("Discard this suggestion")
        }
        .padding(6)
        .background(.quaternary.opacity(0.4), in: .rect(cornerRadius: 5))
    }
}
