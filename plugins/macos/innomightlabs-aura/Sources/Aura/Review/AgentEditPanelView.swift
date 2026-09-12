import SwiftUI

/// The conversation with the agent about this recording — typed, or dictated into the mic.
///
/// One conversation per video, held server-side, so the user can keep talking as they edit
/// without restating what they're working on. The agent never edits directly: it proposes
/// operations, they appear here, and accepting one runs through the same
/// `EditDocumentStore.apply` a drag does — so an AI edit is reviewable before it lands and
/// undoable after.
///
/// The suggested actions are not prompts dressed as buttons. Three of them are computed
/// locally and deterministically; the ones that go to the agent say so by behaving like the
/// rest of the conversation. One is unavailable and admits it.
struct AgentEditPanelView: View {
    @ObservedObject var viewModel: ReviewViewModel
    @StateObject private var voice = VoiceInstructionRecorder()

    @State private var instruction: String = ""
    @State private var showingSettings = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AuraTheme.Space.md) {
                if viewModel.isAgentConfigured {
                    if viewModel.conversation.isEmpty {
                        intro
                    } else {
                        conversation
                    }

                    composer
                    statusLine
                    suggestionList

                    if viewModel.suggestions.isEmpty {
                        actionGrid
                    }
                } else {
                    notConfigured
                }
            }
            .padding(AuraTheme.Space.md)
        }
        .background(AuraTheme.surface)
        .sheet(isPresented: $showingSettings) {
            AgentSettingsView()
        }
    }

    // MARK: - Intro

    private var intro: some View {
        VStack(alignment: .leading, spacing: AuraTheme.Space.sm) {
            HStack(spacing: AuraTheme.Space.sm + 2) {
                Image(systemName: "sparkles")
                    .font(.system(size: 17, weight: .medium))
                    .foregroundStyle(AuraTheme.accent)
                    .frame(width: 38, height: 38)
                    .background {
                        RoundedRectangle(cornerRadius: AuraTheme.Radius.md)
                            .fill(AuraTheme.accentFill(0.18))
                    }

                Text("Hey, I'm Aura")
                    .font(.system(size: 19, weight: .semibold))
                    .foregroundStyle(AuraTheme.textPrimary)
            }

            Text("""
            Your AI editing partner. This video was recorded in Aura, so I already know your \
            screen, camera and audio — and they're all in sync.
            """)
            .font(.system(size: 12))
            .foregroundStyle(AuraTheme.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - Conversation

    private var conversation: some View {
        VStack(alignment: .leading, spacing: AuraTheme.Space.sm) {
            HStack {
                Text("Conversation")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(AuraTheme.textSecondary)
                Spacer()
                Button {
                    viewModel.clearConversationView()
                } label: {
                    Image(systemName: "eraser")
                        .font(.system(size: 10))
                        .foregroundStyle(AuraTheme.textSecondary)
                }
                .buttonStyle(.plain)
                .help("Clear the visible chat (the agent still remembers this recording)")
            }

            ForEach(viewModel.conversation) { turn in
                turnView(turn)
            }
        }
    }

    private func turnView(_ turn: ReviewViewModel.AgentTurn) -> some View {
        HStack(alignment: .top, spacing: AuraTheme.Space.sm) {
            Image(systemName: turn.speaker == .user ? "person.fill" : "sparkles")
                .font(.system(size: 9))
                .foregroundStyle(turn.speaker == .user ? AuraTheme.textTertiary : AuraTheme.accent)
                .frame(width: 14)

            Text(turn.text)
                .font(.system(size: 12))
                .foregroundStyle(turn.speaker == .user ? AuraTheme.textSecondary : AuraTheme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(AuraTheme.Space.sm + 2)
        .background {
            RoundedRectangle(cornerRadius: AuraTheme.Radius.sm)
                .fill(turn.speaker == .user ? Color.clear : AuraTheme.surfaceElevated)
        }
    }

    // MARK: - Composer

    private var composer: some View {
        HStack(spacing: AuraTheme.Space.sm) {
            TextField(
                viewModel.conversation.isEmpty
                    ? "Describe what you want to do…"
                    : "Reply…",
                text: $instruction,
                axis: .vertical
            )
            .textFieldStyle(.plain)
            .font(.system(size: 12))
            .foregroundStyle(AuraTheme.textPrimary)
            .lineLimit(1...4)
            .onSubmit(submit)
            .disabled(viewModel.isAwaitingAgent)

            micButton
            sendButton
        }
        .padding(.horizontal, AuraTheme.Space.sm + 4)
        .padding(.vertical, AuraTheme.Space.sm + 2)
        .background {
            RoundedRectangle(cornerRadius: AuraTheme.Radius.lg)
                .fill(AuraTheme.surfaceElevated)
                .overlay {
                    RoundedRectangle(cornerRadius: AuraTheme.Radius.lg)
                        .stroke(AuraTheme.border, lineWidth: 1)
                }
        }
    }

    private var canSend: Bool {
        !instruction.trimmingCharacters(in: .whitespaces).isEmpty && !viewModel.isAwaitingAgent
    }

    private var sendButton: some View {
        Button(action: submit) {
            Image(systemName: "arrow.right")
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(canSend ? AuraTheme.textPrimary : AuraTheme.textTertiary)
                .frame(width: 26, height: 26)
                .background {
                    Circle().fill(canSend ? AuraTheme.accent : AuraTheme.surface)
                }
        }
        .buttonStyle(.plain)
        .disabled(!canSend)
        .help("Send")
    }

    private var micButton: some View {
        Button(action: toggleDictation) {
            Image(systemName: voice.state == .listening ? "mic.fill" : "mic")
                .font(.system(size: 11))
                .foregroundStyle(voice.state == .listening ? ReviewPalette.cut : AuraTheme.textSecondary)
                .frame(width: 22, height: 22)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(voice.state == .transcribing || viewModel.isAwaitingAgent)
        .help(voice.state == .listening ? "Stop dictating" : "Dictate an instruction")
    }

    // MARK: - Suggested actions

    private var actionGrid: some View {
        LazyVGrid(
            columns: [GridItem(.flexible(), spacing: AuraTheme.Space.sm),
                      GridItem(.flexible(), spacing: AuraTheme.Space.sm)],
            spacing: AuraTheme.Space.sm
        ) {
            ForEach(StudioAction.allCases) { action in
                actionCard(action)
            }
        }
    }

    private func actionCard(_ action: StudioAction) -> some View {
        let available = !isUnavailable(action)

        return Button {
            viewModel.perform(action)
        } label: {
            VStack(alignment: .leading, spacing: AuraTheme.Space.xs + 2) {
                Image(systemName: action.symbol)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(available ? AuraTheme.accent : AuraTheme.textTertiary)

                Text(action.title)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(available ? AuraTheme.textPrimary : AuraTheme.textTertiary)

                Text(action.subtitle)
                    .font(.system(size: 10))
                    .foregroundStyle(AuraTheme.textTertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(AuraTheme.Space.sm + 2)
            .background {
                RoundedRectangle(cornerRadius: AuraTheme.Radius.md)
                    .fill(AuraTheme.surfaceElevated)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!available || viewModel.isAwaitingAgent)
        .help(helpText(action))
    }

    private func isUnavailable(_ action: StudioAction) -> Bool {
        if case .unavailable = action.kind { return true }
        return false
    }

    private func helpText(_ action: StudioAction) -> String {
        switch action.kind {
        case .unavailable(let reason): return reason
        case .local: return "\(action.title) — computed here, one undo step"
        case .agent: return "\(action.title) — asks the agent, then you review each edit"
        }
    }

    // MARK: - Status and suggestions

    @ViewBuilder
    private var statusLine: some View {
        switch viewModel.agentState {
        case .thinking:
            HStack(spacing: AuraTheme.Space.sm) {
                ProgressView().controlSize(.small)
                Text("Thinking…")
                    .font(.system(size: 11))
                    .foregroundStyle(AuraTheme.textSecondary)
            }

        case .failed(let reason):
            Text(reason)
                .font(.system(size: 11))
                .foregroundStyle(ReviewPalette.cut)
                .fixedSize(horizontal: false, vertical: true)

        case .idle:
            switch voice.state {
            case .listening:
                Text("Listening… click the mic again when you're done.")
                    .font(.system(size: 11))
                    .foregroundStyle(AuraTheme.textSecondary)
            case .transcribing:
                HStack(spacing: AuraTheme.Space.sm) {
                    ProgressView().controlSize(.small)
                    Text("Transcribing…")
                        .font(.system(size: 11))
                        .foregroundStyle(AuraTheme.textSecondary)
                }
            case .failed(let reason):
                Text(reason)
                    .font(.system(size: 11))
                    .foregroundStyle(ReviewPalette.cut)
            case .idle:
                EmptyView()
            }
        }
    }

    @ViewBuilder
    private var suggestionList: some View {
        if !viewModel.suggestions.isEmpty {
            VStack(alignment: .leading, spacing: AuraTheme.Space.sm) {
                HStack {
                    Text("\(viewModel.suggestions.count) proposed")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(AuraTheme.textSecondary)
                    Spacer()
                    Button("Apply All") { viewModel.acceptAllSuggestions() }
                        .buttonStyle(.plain)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(AuraTheme.accent)
                    Button("Dismiss") { viewModel.dismissSuggestions() }
                        .buttonStyle(.plain)
                        .font(.system(size: 11))
                        .foregroundStyle(AuraTheme.textSecondary)
                }

                ForEach(viewModel.suggestions) { suggestion in
                    SuggestionRow(
                        suggestion: suggestion,
                        onAccept: { viewModel.accept(suggestion) },
                        onReject: { viewModel.reject(suggestion) }
                    )
                }
            }
        }
    }

    private var notConfigured: some View {
        VStack(alignment: .leading, spacing: AuraTheme.Space.sm) {
            Text("Connect your agent to edit by asking.")
                .font(.system(size: 12))
                .foregroundStyle(AuraTheme.textSecondary)
            Button("Agent Settings…") { showingSettings = true }
                .buttonStyle(.plain)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(AuraTheme.accent)
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
        HStack(alignment: .top, spacing: AuraTheme.Space.sm) {
            VStack(alignment: .leading, spacing: 2) {
                Text(EditOperationDescription.summary(suggestion.operation))
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(AuraTheme.textPrimary)
                if let rationale = suggestion.rationale {
                    Text(rationale)
                        .font(.system(size: 10))
                        .foregroundStyle(AuraTheme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Button(action: onAccept) {
                Image(systemName: "checkmark")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(AuraTheme.accent)
                    .frame(width: 22, height: 22)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("Apply this edit")

            Button(action: onReject) {
                Image(systemName: "xmark")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(AuraTheme.textSecondary)
                    .frame(width: 22, height: 22)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("Discard this suggestion")
        }
        .padding(AuraTheme.Space.sm + 2)
        .background {
            RoundedRectangle(cornerRadius: AuraTheme.Radius.sm)
                .fill(AuraTheme.surfaceElevated)
        }
    }
}
