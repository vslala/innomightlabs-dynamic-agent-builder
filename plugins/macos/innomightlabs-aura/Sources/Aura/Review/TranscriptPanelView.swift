import SwiftUI

/// The transcript, tracking the playhead.
///
/// Highlighting is driven by `activeCueID`, which the view model publishes only when the
/// active cue actually changes rather than on every tick, so this list is not rebuilt 30
/// times a second.
struct TranscriptPanelView: View {
    @ObservedObject var viewModel: ReviewViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header

            Divider()

            switch viewModel.transcriptState {
            case .ready:
                if let transcript = viewModel.transcript, !transcript.segments.isEmpty {
                    cues(transcript)
                } else {
                    message("No speech was found in this recording.")
                }

            case .transcribing:
                VStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Transcribing…")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            case .absent:
                message("This session has no microphone track to transcribe.")

            case .failed(let reason):
                VStack(spacing: 8) {
                    Text(reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Try Again") { viewModel.retryTranscription() }
                        .font(.caption)
                }
                .padding(20)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }

    private var header: some View {
        HStack {
            Text("Transcript")
                .font(.headline)
            Spacer()
            if viewModel.excludedWordCount > 0 {
                Button {
                    viewModel.restoreAllWords()
                } label: {
                    Text("\(viewModel.excludedWordCount) cut")
                        .font(.caption2)
                }
                .buttonStyle(.borderless)
                .help("Restore every cut word")
            }
        }
        .padding(10)
    }

    private func message(_ text: String) -> some View {
        Text(text)
            .font(.caption)
            .foregroundStyle(.secondary)
            .multilineTextAlignment(.center)
            .padding(20)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func cues(_ transcript: Transcript) -> some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 2) {
                    ForEach(transcript.segments) { segment in
                        cue(segment)
                            .id(segment.id)
                    }
                }
                .padding(8)
            }
            .onChange(of: viewModel.activeCueID) { _, id in
                guard let id else { return }
                withAnimation(.easeOut(duration: 0.2)) {
                    proxy.scrollTo(id, anchor: .center)
                }
            }
        }
    }

    private func cue(_ segment: Transcript.Segment) -> some View {
        // A cue whose content was cut maps to no composition time at all. Showing it struck
        // through is more use than hiding it — it tells the user what they removed.
        let spans = viewModel.compositionSpans(for: segment)
        let isRemoved = spans.isEmpty
        let isActive = viewModel.activeCueID == segment.id

        return VStack(alignment: .leading, spacing: 2) {
            Text(TimeFormatting.timecode(spans.first?.start ?? segment.start))
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(.tertiary)

            if segment.words.isEmpty {
                Text(segment.text)
                    .font(.callout)
                    .strikethrough(isRemoved)
                    .foregroundStyle(isRemoved ? .secondary : .primary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                words(segment, cueRemoved: isRemoved)
            }
        }
        .padding(6)
        .background(isActive ? Color.accentColor.opacity(0.18) : .clear, in: .rect(cornerRadius: 5))
        .contentShape(Rectangle())
        .onTapGesture { viewModel.seek(to: segment) }
        .contextMenu {
            Button("Remove This Whole Line", systemImage: "scissors") {
                viewModel.removeRange(of: segment)
            }
            .disabled(isRemoved)
        }
    }

    /// Word-by-word, so a single word can be cut or brought back by clicking it. Cutting
    /// words is reversible by design — a struck-through word is still there, just excluded —
    /// which is why this reads as a toggle rather than a delete.
    private func words(_ segment: Transcript.Segment, cueRemoved: Bool) -> some View {
        FlowLayout(spacing: 3, lineSpacing: 2) {
            ForEach(segment.words) { word in
                let cut = viewModel.isWordExcluded(word)
                Text(word.text)
                    .font(.callout)
                    .strikethrough(cut || cueRemoved)
                    .foregroundStyle(cut || cueRemoved ? .secondary : .primary)
                    .padding(.horizontal, 1)
                    .background(
                        cut ? Color.red.opacity(0.12) : .clear,
                        in: .rect(cornerRadius: 3)
                    )
                    .onTapGesture { viewModel.toggleWord(word) }
                    .help(cut ? "Click to bring “\(word.text)” back" : "Click to cut “\(word.text)”")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
