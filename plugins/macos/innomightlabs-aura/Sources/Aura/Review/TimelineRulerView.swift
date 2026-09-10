import SwiftUI

/// Scrub bar with clip boundaries and session markers.
///
/// Markers come from `events.jsonl` and are placed by media time, then mapped through the
/// time map — so a marker still points at the moment it was made even after cuts move it.
struct TimelineRulerView: View {
    @ObservedObject var viewModel: ReviewViewModel

    @State private var isScrubbing = false

    var body: some View {
        GeometryReader { geometry in
            let duration = Timeline.seconds(viewModel.duration)
            let width = geometry.size.width

            ZStack(alignment: .leading) {
                Capsule()
                    .fill(.quaternary)
                    .frame(height: 6)

                Capsule()
                    .fill(.tint)
                    .frame(width: max(0, fraction(duration) * width), height: 6)

                ForEach(clipBoundaries(), id: \.self) { boundary in
                    Rectangle()
                        .fill(.secondary)
                        .frame(width: 1, height: 14)
                        .offset(x: boundary / max(duration, 0.001) * width)
                }

                ForEach(markers(), id: \.time) { marker in
                    Image(systemName: "flag.fill")
                        .font(.system(size: 8))
                        .foregroundStyle(.orange)
                        .offset(x: marker.time / max(duration, 0.001) * width - 4)
                        .help(marker.label)
                }

                Circle()
                    .fill(.white)
                    .shadow(radius: 1)
                    .frame(width: 11, height: 11)
                    .offset(x: fraction(duration) * width - 5.5)
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
                        viewModel.scrub(to: seconds(at: value.location.x, width: width, duration: duration))
                    }
                    .onEnded { value in
                        viewModel.commitScrub(to: seconds(at: value.location.x, width: width, duration: duration))
                        isScrubbing = false
                    }
            )
        }
    }

    private func fraction(_ duration: TimeInterval) -> Double {
        guard duration > 0 else { return 0 }
        return min(1, max(0, Timeline.seconds(viewModel.playhead) / duration))
    }

    private func seconds(at x: CGFloat, width: CGFloat, duration: TimeInterval) -> TimeInterval {
        guard width > 0 else { return 0 }
        return min(duration, max(0, Double(x / width) * duration))
    }

    /// Internal cut points, i.e. every clip start except the first.
    private func clipBoundaries() -> [Double] {
        guard let segments = viewModel.timeline?.timeMap.segments else { return [] }
        return segments.dropFirst().map { Timeline.seconds($0.composition.start) }
    }

    private func markers() -> [(time: Double, label: String)] {
        guard let timeline = viewModel.timeline else { return [] }
        return viewModel.markers.compactMap { marker in
            // Source ranges are half-open, so a marker made in the instant before Stop maps
            // to nothing; clamp it to the end rather than dropping the flag.
            let composition = timeline.timeMap.compositionTimes(forSource: marker.mediaTs).first
                ?? (marker.mediaTs >= lastSourceEnd(timeline) ? Timeline.seconds(timeline.duration) : nil)
            guard let composition else { return nil }
            return (composition, marker.event.label ?? "Marker")
        }
    }

    private func lastSourceEnd(_ timeline: ResolvedTimeline) -> TimeInterval {
        timeline.timeMap.segments.last.map { Timeline.seconds($0.source.end) } ?? 0
    }
}
