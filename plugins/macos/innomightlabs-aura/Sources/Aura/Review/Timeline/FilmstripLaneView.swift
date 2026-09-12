import SwiftUI

/// A thumbnail strip for one video lane.
///
/// Frames are placed by **source time**, like every other lane, so a cut lines up across the
/// whole timeline. Each slot asks the strip for whichever frame covers its own moment, rather
/// than laying frames out end to end — that way zooming changes how much of the recording a
/// thumbnail represents instead of scrolling a fixed ribbon out of alignment.
struct FilmstripLaneView: View {
    let frames: FilmstripFrames?
    let window: StampSpan<Source>
    let height: CGFloat

    var body: some View {
        GeometryReader { geometry in
            let width = geometry.size.width

            Canvas { context, size in
                guard let frames, width > 0, window.duration > 0 else { return }

                let slotWidth = max(24, height * frames.frameAspect)
                var x: CGFloat = 0

                while x < size.width {
                    let fraction = Double((x + slotWidth / 2) / width)
                    let source = window.stamp(atFraction: fraction)
                    guard let index = frameIndex(frames, at: source) else {
                        x += slotWidth
                        continue
                    }

                    // Zoomed far out, consecutive slots resolve to the same frame. Drawn
                    // anyway — repeating it is what that stretch of recording looks like, and
                    // the decode is cached, so the alternative would be gaps.
                    if let image = frames.image(at: index) {
                        context.draw(
                            Image(decorative: image, scale: 1),
                            in: CGRect(x: x, y: 0, width: slotWidth, height: size.height)
                        )
                    }
                    x += slotWidth
                }
            }
            .frame(height: height)
            .clipShape(RoundedRectangle(cornerRadius: AuraTheme.Radius.sm))
            .background {
                RoundedRectangle(cornerRadius: AuraTheme.Radius.sm)
                    .fill(AuraTheme.surfaceElevated)
            }
            .overlay {
                if frames == nil {
                    // Extraction runs after the window is playable, so this is the normal
                    // first-open state rather than an error.
                    RoundedRectangle(cornerRadius: AuraTheme.Radius.sm)
                        .fill(AuraTheme.surfaceElevated)
                        .overlay {
                            ProgressView().controlSize(.small)
                        }
                }
            }
        }
        .frame(height: height)
    }

    private func frameIndex(_ frames: FilmstripFrames, at source: Stamp<Source>) -> Int? {
        guard frames.interval > 0, source.seconds >= 0 else { return nil }
        let index = Int(source.seconds / frames.interval)
        return index < frames.frameCount ? index : nil
    }
}
