import SwiftUI

/// A slim scrubber directly under the picture, on the **edited** timeline.
///
/// Quiet by design — a 3pt line that thickens on hover — because the timeline below is where
/// precise work happens. This is for coarse navigation while watching.
///
/// It shows splits and markers but not cut boundaries: a real document has 40-odd of those, and
/// over a few hundred points they read as a grey smear. Cuts belong to the timeline's lanes,
/// where there is room to see them.
struct PreviewScrubBar: View {
    @ObservedObject var viewModel: ReviewViewModel

    @State private var isScrubbing = false
    @State private var isHovering = false

    private var edited: StampSpan<Composition> { viewModel.projection.edited }
    private var height: CGFloat { isHovering || isScrubbing ? 6 : 3 }

    var body: some View {
        GeometryReader { geometry in
            let width = geometry.size.width

            ZStack(alignment: .leading) {
                Capsule()
                    .fill(AuraTheme.surfaceElevated)
                    .frame(height: height)

                Capsule()
                    .fill(AuraTheme.accent)
                    .frame(width: max(0, playheadFraction * width), height: height)

                splits(width: width)
                markers(width: width)

                if isHovering || isScrubbing {
                    Circle()
                        .fill(AuraTheme.textPrimary)
                        .frame(width: 11, height: 11)
                        .shadow(color: .black.opacity(0.5), radius: 2)
                        .offset(x: playheadFraction * width - 5.5)
                }
            }
            .frame(maxHeight: .infinity)
            .contentShape(Rectangle())
            .onHover { isHovering = $0 }
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { value in
                        if !isScrubbing {
                            isScrubbing = true
                            viewModel.pause()
                        }
                        viewModel.scrub(to: stamp(atX: value.location.x, width: width).seconds)
                    }
                    .onEnded { value in
                        viewModel.commitScrub(to: stamp(atX: value.location.x, width: width).seconds)
                        isScrubbing = false
                    }
            )
            .animation(.easeOut(duration: 0.12), value: height)
        }
        .frame(height: 14)
    }

    private var playheadFraction: Double {
        edited.fraction(of: Stamp(viewModel.playhead))
    }

    private func stamp(atX x: CGFloat, width: CGFloat) -> Stamp<Composition> {
        guard width > 0 else { return edited.start }
        return edited.stamp(atFraction: Double(x / width))
    }

    /// A split's own time is in the recording's clock, so its position here comes from the
    /// projection rather than being used directly.
    private func splits(width: CGFloat) -> some View {
        ForEach(viewModel.projection.splits, id: \.seconds) { split in
            if let composition = viewModel.projection.compositionTime(forSource: split) {
                Rectangle()
                    .fill(ReviewPalette.split)
                    .frame(width: 1, height: height + 4)
                    .offset(x: edited.fraction(of: composition) * width)
                    .allowsHitTesting(false)
            }
        }
    }

    private func markers(width: CGFloat) -> some View {
        ForEach(viewModel.projection.markers) { marker in
            if let composition = marker.composition {
                Circle()
                    .fill(marker.isEditorial
                          ? ReviewPalette.editorialMarker
                          : ReviewPalette.recordingMarker)
                    .frame(width: 5, height: 5)
                    .offset(x: edited.fraction(of: composition) * width - 2.5)
                    .help(marker.label.isEmpty ? "Marker" : marker.label)
                    // Simultaneous, not `.onTapGesture`: a child gesture outranks the scrub
                    // drag, so each marker would punch a hole where scrubbing cannot begin.
                    .simultaneousGesture(TapGesture().onEnded { viewModel.seek(to: marker) })
            }
        }
    }
}
