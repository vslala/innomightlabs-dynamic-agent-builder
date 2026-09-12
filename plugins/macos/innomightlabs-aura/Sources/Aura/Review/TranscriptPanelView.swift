import SwiftUI

/// The transcript, word by word, tracking the playhead.
///
/// Every time it shows and every cut/active decision comes from the projection, so the panel
/// holds no clock arithmetic of its own — an earlier version rendered composition time
/// normally but fell back to *transcript* time for a fully-cut cue, putting two different
/// clocks in one column.
struct TranscriptPanelView: View {
    @ObservedObject var viewModel: ReviewViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()

            switch viewModel.transcriptState {
            case .ready:
                if viewModel.projection.cues.isEmpty {
                    message("No speech was found in this recording.")
                } else {
                    cues
                }

            case .transcribing:
                VStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Transcribing…").font(.caption).foregroundStyle(.secondary)
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
            Text("Transcript").font(.headline)
            Spacer()
            if viewModel.cutWordCount > 0 {
                Button {
                    viewModel.restoreAllWords()
                } label: {
                    Text("\(viewModel.cutWordCount) cut").font(.caption2)
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

    private var cues: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 2) {
                    ForEach(viewModel.projection.cues) { cue in
                        cueRow(cue).id(cue.id)
                    }
                }
                .padding(8)
            }
            .onChange(of: viewModel.activeCueID) { _, id in
                guard let id else { return }
                withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo(id, anchor: .center) }
            }
        }
    }

    private func cueRow(_ cue: ProjectedCue) -> some View {
        let isActive = viewModel.activeCueID == cue.id
        let words = viewModel.projection.words.filter { cue.wordIDs.contains($0.id) }

        return VStack(alignment: .leading, spacing: 2) {
            // Always the edited timeline's clock — or the recording's, clearly marked, when
            // the line no longer appears in the edit at all.
            Text(cue.composition.first
                 .map { TimeFormatting.timecode($0.start.seconds) }
                 ?? "cut · \(TimeFormatting.timecode(cue.source.start.seconds))")
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(.tertiary)

            FlowLayout(spacing: 3, lineSpacing: 2) {
                ForEach(words) { word in
                    wordView(word)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(6)
        .background(isActive ? ReviewPalette.activeWord.opacity(0.12) : .clear, in: .rect(cornerRadius: 5))
        .contentShape(Rectangle())
        .contextMenu {
            Button("Remove This Whole Line", systemImage: "scissors") {
                viewModel.cut(cue: cue)
            }
            .disabled(cue.isCut)
            Button("Mark Here", systemImage: "bookmark") {
                viewModel.addMarker(at: cue.source.start, label: String(cue.text.prefix(40)))
            }
        }
    }

    /// One tappable word. Cut words are struck through and tinted with the same token the
    /// waveform shades cut regions with, so the two read as the same thing.
    private func wordView(_ word: ProjectedWord) -> some View {
        let isActive = viewModel.activeWordID == word.id

        return Text(word.text)
            .font(.callout)
            .strikethrough(word.isCut)
            .foregroundStyle(word.isCut ? .secondary : .primary)
            .padding(.horizontal, 2)
            .background(
                word.isCut
                    ? ReviewPalette.cut.opacity(0.14)
                    : (isActive ? ReviewPalette.activeWord.opacity(0.3) : .clear),
                in: .rect(cornerRadius: 3)
            )
            .onTapGesture { viewModel.toggle(word: word) }
            .help(word.isCut
                  ? "Click to bring “\(word.text)” back"
                  : "Click to cut “\(word.text)”")
    }
}
