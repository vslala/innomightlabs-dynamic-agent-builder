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

            switch viewModel.transcriptState {
            case .ready:
                if viewModel.projection.cues.isEmpty {
                    message("No speech was found in this recording.")
                } else {
                    cues
                }

            case .transcribing:
                VStack(spacing: AuraTheme.Space.sm) {
                    ProgressView().controlSize(.small)
                    Text("Transcribing…")
                        .font(.system(size: 12))
                        .foregroundStyle(AuraTheme.textSecondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            case .absent:
                message("This session has no microphone track to transcribe.")

            case .failed(let reason):
                VStack(spacing: AuraTheme.Space.sm) {
                    Text(reason)
                        .font(.system(size: 12))
                        .foregroundStyle(AuraTheme.textSecondary)
                        .multilineTextAlignment(.center)
                    Button("Try Again") { viewModel.retryTranscription() }
                        .buttonStyle(.plain)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(AuraTheme.accent)
                }
                .padding(AuraTheme.Space.lg)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }

    private var header: some View {
        HStack {
            Text("Click a word to cut it")
                .font(.system(size: 11))
                .foregroundStyle(AuraTheme.textTertiary)
            Spacer()
            if viewModel.cutWordCount > 0 {
                Button {
                    viewModel.restoreAllWords()
                } label: {
                    Text("\(viewModel.cutWordCount) cut")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(ReviewPalette.cut)
                        .padding(.horizontal, AuraTheme.Space.sm)
                        .padding(.vertical, 3)
                        .background { Capsule().fill(ReviewPalette.cut.opacity(0.16)) }
                }
                .buttonStyle(.plain)
                .help("Restore every cut word")
            }
        }
        .padding(.horizontal, AuraTheme.Space.md)
        .padding(.vertical, AuraTheme.Space.sm + 2)
    }

    private func message(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 12))
            .foregroundStyle(AuraTheme.textSecondary)
            .multilineTextAlignment(.center)
            .padding(AuraTheme.Space.lg)
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
                .foregroundStyle(cue.isCut ? ReviewPalette.cut.opacity(0.8) : AuraTheme.textTertiary)

            FlowLayout(spacing: 3, lineSpacing: 2) {
                ForEach(words) { word in
                    wordView(word)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(AuraTheme.Space.sm)
        .background {
            RoundedRectangle(cornerRadius: AuraTheme.Radius.sm)
                .fill(isActive ? AuraTheme.accentFill(0.16) : .clear)
        }
        .contentShape(Rectangle())
        .contextMenu {
            Button("Remove Section", systemImage: "scissors") {
                viewModel.cut(cue: cue)
            }
            .disabled(cue.isCut)
            Button("Go to This Line", systemImage: "arrow.right.circle") {
                viewModel.seek(toCue: cue)
            }
            .disabled(cue.isCut)
            Button("Add Marker Here", systemImage: "bookmark") {
                viewModel.addMarker(at: cue.source.start, label: String(cue.text.prefix(40)))
            }
            Divider()
            Button("Ask Aura About This", systemImage: "sparkles") {
                viewModel.askAboutCue(cue)
            }
        }
    }

    /// One tappable word. Cut words are struck through and tinted with the same token the
    /// waveform shades cut regions with, so the two read as the same thing.
    private func wordView(_ word: ProjectedWord) -> some View {
        let isActive = viewModel.activeWordID == word.id

        return Text(word.text)
            .font(.system(size: 13))
            .strikethrough(word.isCut)
            .foregroundStyle(word.isCut ? AuraTheme.textTertiary : AuraTheme.textPrimary)
            .padding(.horizontal, 2)
            .background(
                word.isCut
                    ? ReviewPalette.cut.opacity(0.18)
                    : (isActive ? AuraTheme.accentFill(0.35) : .clear),
                in: .rect(cornerRadius: 3)
            )
            .onTapGesture { viewModel.toggle(word: word) }
            .help(word.isCut
                  ? "Click to bring “\(word.text)” back"
                  : "Click to cut “\(word.text)”")
    }
}
