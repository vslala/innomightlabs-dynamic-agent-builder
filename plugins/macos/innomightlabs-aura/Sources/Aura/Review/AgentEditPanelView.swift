import SwiftUI

/// The conversation with the agent about this recording — typed, or dictated into the mic.
///
/// One conversation per video, held server-side, so the user can keep talking as they edit
/// without restating what they're working on. The agent never edits directly: it proposes
/// operations, they appear here, and accepting one runs through the same
/// `EditDocumentStore.apply` a drag does — so an AI edit is reviewable before it lands and
/// undoable after.
struct AgentEditPanelView: View {
    @ObservedObject var viewModel: ReviewViewModel
    @StateObject private var voice = VoiceInstructionRecorder()

    @State private var instruction: String = ""
    @State private var showingSettings = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            header

            if viewModel.isAgentConfigured {
                if !viewModel.conversation.isEmpty {
                    conversation
                }
                suggestionList
                statusLine
                composer
            } else {
                notConfigured
            }
        }
        .padding(10)
        .sheet(isPresented: $showingSettings) {
            AgentSettingsView()
        }
    }

    private var header: some View {
        HStack {
            Label("Ask Aura", systemImage: "sparkles")
                .font(.headline)
            Spacer()
            if !viewModel.conversation.isEmpty {
                Button {
                    viewModel.clearConversationView()
                } label: {
                    Image(systemName: "eraser")
                }
                .buttonStyle(.borderless)
                .help("Clear the visible chat (the agent still remembers this recording)")
            }
            Button {
                showingSettings = true
            } label: {
                Image(systemName: "gearshape")
            }
            .buttonStyle(.borderless)
            .help("Agent settings")
        }
    }

    private var conversation: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(viewModel.conversation) { turn in
                        turnView(turn).id(turn.id)
                    }
                }
                .padding(.vertical, 2)
            }
            .frame(maxHeight: 180)
            .onChange(of: viewModel.conversation.count) { _, _ in
                guard let last = viewModel.conversation.last else { return }
                withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo(last.id, anchor: .bottom) }
            }
        }
    }

    private func turnView(_ turn: ReviewViewModel.AgentTurn) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: turn.speaker == .user ? "person.fill" : "sparkles")
                .font(.system(size: 9))
                .foregroundStyle(.tertiary)
                .frame(width: 12)

            Text(turn.text)
                .font(.caption)
                .foregroundStyle(turn.speaker == .user ? .secondary : .primary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var composer: some View {
        HStack(spacing: 6) {
            TextField(
                viewModel.conversation.isEmpty
                    ? "e.g. cut the false start, and hide the camera while the terminal is up"
                    : "Reply…",
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
            .help("Send")
        }
    }

    private var micButton: some View {
        Button {
            toggleDictation()
        } label: {
            Image(systemName: voice.state == .listening ? "mic.fill" : "mic")
                .foregroundStyle(voice.state == .listening ? .red : .primary)
        }
        .buttonStyle(.borderless)
        .disabled(voice.state == .transcribing || viewModel.isAwaitingAgent)
        .help(voice.state == .listening ? "Stop dictating" : "Dictate an instruction")
    }

    @ViewBuilder
    private var statusLine: some View {
        switch viewModel.agentState {
        case .thinking:
            HStack(spacing: 6) {
                ProgressView().controlSize(.small)
                Text("Thinking…").font(.caption2).foregroundStyle(.secondary)
            }

        case .failed(let reason):
            Text(reason)
                .font(.caption2)
                .foregroundStyle(.red)
                .fixedSize(horizontal: false, vertical: true)

        case .idle:
            switch voice.state {
            case .listening:
                Text("Listening… click the mic again when you're done.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            case .transcribing:
                HStack(spacing: 6) {
                    ProgressView().controlSize(.small)
                    Text("Transcribing…").font(.caption2).foregroundStyle(.secondary)
                }
            case .failed(let reason):
                Text(reason).font(.caption2).foregroundStyle(.red)
            case .idle:
                EmptyView()
            }
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
                Button("Dismiss") { viewModel.dismissSuggestions() }
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
