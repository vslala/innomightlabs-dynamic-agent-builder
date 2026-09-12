import SwiftUI

/// The scrub bar, on the **edited** timeline — this is the transport, so it shows what plays.
///
/// It draws splits and markers only. Cut stitches belong to the waveform lane: a real document
/// has 40-odd cut boundaries, which over a few hundred points is a grey smear, and `ForEach`
/// over rounded times would collide and silently drop duplicates.
struct TimelineRulerView: View {
    @ObservedObject var viewModel: ReviewViewModel

    @State private var isScrubbing = false
    /// The marker whose rename field is open. Transient UI state, deliberately not in the
    /// view model: an abandoned rename must leave no trace in the document or the undo stack.
    @State private var renaming: ProjectedMarker?
    @State private var draftLabel = ""

    private var edited: StampSpan<Composition> { viewModel.projection.edited }

    var body: some View {
        GeometryReader { geometry in
            let width = geometry.size.width

            ZStack(alignment: .leading) {
                Capsule()
                    .fill(.quaternary)
                    .frame(height: 6)

                Capsule()
                    .fill(.tint)
                    .frame(width: max(0, playheadFraction * width), height: 6)

                splits(width: width)
                markers(width: width)

                Circle()
                    .fill(.white)
                    .shadow(radius: 1)
                    .frame(width: 11, height: 11)
                    .offset(x: playheadFraction * width - 5.5)
            }
            .frame(maxHeight: .infinity)
            .contentShape(Rectangle())
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
        }
    }

    private var playheadFraction: Double {
        edited.fraction(of: Stamp(viewModel.playhead))
    }

    private func stamp(atX x: CGFloat, width: CGFloat) -> Stamp<Composition> {
        guard width > 0 else { return edited.start }
        return edited.stamp(atFraction: Double(x / width))
    }

    /// User-meaningful edit boundaries. Their composition position comes from the projection,
    /// since a split's own time is in the recording's clock.
    private func splits(width: CGFloat) -> some View {
        ForEach(viewModel.projection.splits, id: \.seconds) { split in
            if let composition = viewModel.projection.compositionTime(forSource: split) {
                Rectangle()
                    .fill(ReviewPalette.split)
                    .frame(width: 1, height: 14)
                    .offset(x: edited.fraction(of: composition) * width)
            }
        }
    }

    private func markers(width: CGFloat) -> some View {
        ForEach(viewModel.projection.markers) { marker in
            if let composition = marker.composition {
                Image(systemName: marker.isEditorial ? "bookmark.fill" : "flag.fill")
                    .font(.system(size: 8))
                    .foregroundStyle(marker.isEditorial
                                     ? ReviewPalette.editorialMarker
                                     : ReviewPalette.recordingMarker)
                    // A 8pt glyph is a small target; widen the hit area without moving it.
                    .frame(width: 14, height: 14)
                    .contentShape(Rectangle())
                    .offset(x: edited.fraction(of: composition) * width - 7)
                    .help(markerHelp(marker))
                    // Simultaneous, not `.onTapGesture`: a child gesture outranks the scrub
                    // bar's drag, so each marker would otherwise punch a 14pt hole in the
                    // transport where scrubbing cannot begin.
                    .simultaneousGesture(TapGesture().onEnded { viewModel.seek(to: marker) })
                    .contextMenu { markerMenu(marker) }
                    .popover(isPresented: renameBinding(for: marker), arrowEdge: .bottom) {
                        renameField(marker)
                    }
            }
        }
    }

    @ViewBuilder
    private func markerMenu(_ marker: ProjectedMarker) -> some View {
        Button("Go to Marker") { viewModel.seek(to: marker) }

        if marker.isEditorial {
            Divider()
            Button("Rename…") {
                draftLabel = marker.label
                renaming = marker
            }
            Button("Move Here") { viewModel.moveMarker(marker, to: playheadSource) }
                .disabled(playheadSource == marker.source)
            Button("Delete", role: .destructive) { viewModel.removeMarker(marker) }
        } else {
            Divider()
            // Stated rather than silently absent, so the greyed-out menu explains itself.
            Text("Logged while recording — not editable")
        }
    }

    private func renameField(_ marker: ProjectedMarker) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Marker name").font(.caption).foregroundStyle(.secondary)
            TextField("Name", text: $draftLabel)
                .textFieldStyle(.roundedBorder)
                .frame(width: 180)
                .onSubmit { commitRename(marker) }
            HStack {
                Spacer()
                Button("Cancel") { renaming = nil }
                Button("Save") { commitRename(marker) }.keyboardShortcut(.defaultAction)
            }
        }
        .padding(12)
    }

    private func commitRename(_ marker: ProjectedMarker) {
        let trimmed = draftLabel.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed != marker.label {
            viewModel.renameMarker(marker, to: trimmed)
        }
        renaming = nil
    }

    /// One popover per marker, driven off a single piece of state — otherwise every marker in
    /// the ForEach binds the same `isPresented` and they all open together.
    private func renameBinding(for marker: ProjectedMarker) -> Binding<Bool> {
        Binding(
            get: { renaming?.id == marker.id },
            set: { if !$0, renaming?.id == marker.id { renaming = nil } }
        )
    }

    /// The playhead in recording time, which is the clock markers live on.
    private var playheadSource: Stamp<Source> { viewModel.playheadSourceStamp }

    private func markerHelp(_ marker: ProjectedMarker) -> String {
        let name = marker.label.isEmpty ? "Marker" : marker.label
        return marker.isEditorial ? name : "\(name) (logged while recording)"
    }
}
