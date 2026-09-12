import SwiftUI

/// Caption blocks, one per transcript cue, on the shared source axis.
///
/// Directly above Screen because a caption is about what is being said over the picture, and
/// the two are read together. Clicking a block is the same code path as clicking a transcript
/// line — there is one notion of "go to this cue".
struct CaptionLaneView: View {
    @ObservedObject var viewModel: ReviewViewModel
    let window: StampSpan<Source>
    let height: CGFloat

    var body: some View {
        GeometryReader { geometry in
            let width = geometry.size.width

            ZStack(alignment: .leading) {
                ForEach(visibleCues) { cue in
                    block(cue, width: width)
                }
            }
            .frame(width: width, height: height, alignment: .leading)
        }
        .frame(height: height)
    }

    private var visibleCues: [ProjectedCue] {
        viewModel.projection.cues.filter { $0.source.overlaps(window) }
    }

    private func block(_ cue: ProjectedCue, width: CGFloat) -> some View {
        let start = window.fraction(of: cue.source.start) * width
        let end = window.fraction(of: cue.source.end) * width
        // A gap between blocks so adjacent cues read as separate; a floor so a short cue is
        // still clickable.
        let blockWidth = max(16, end - start - 3)

        return Text(cue.text)
            .font(.system(size: 10))
            .foregroundStyle(cue.isCut ? AuraTheme.textTertiary : AuraTheme.textPrimary)
            .strikethrough(cue.isCut)
            .lineLimit(1)
            .truncationMode(.tail)
            .padding(.horizontal, 6)
            .frame(width: blockWidth, height: height - 6, alignment: .leading)
            .background {
                RoundedRectangle(cornerRadius: 6)
                    .fill(cue.isCut
                          ? ReviewPalette.cut.opacity(0.16)
                          : AuraTheme.accentFill(0.16))
            }
            .overlay {
                if viewModel.projection.cue(atComposition: Stamp(viewModel.playhead))?.id == cue.id {
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(AuraTheme.accent, lineWidth: 1)
                }
            }
            .offset(x: start)
            .help(cue.text)
            // Simultaneous so the timeline's own selection drag still starts here.
            .simultaneousGesture(TapGesture().onEnded { viewModel.seek(toCue: cue) })
    }
}
