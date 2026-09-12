import SwiftUI

/// Draws a peak envelope over a window of the **recording**.
///
/// Buckets are indexed from `peaksStart`, which is where bucket 0 sits **in source time**.
/// The whole-file cache is bucketed in that lane's own audio-file time, so its bucket 0 is at
/// the lane offset; a detail read is already bucketed from the window's start.
///
/// Typed as a `Stamp<Source>` rather than a bare `TimeInterval` on purpose: the audio-file
/// clock is a fourth clock, and when this parameter was untyped the two call-site branches
/// passed values from *different* clocks into it — one of them sign-flipped.
struct WaveformTrace: View, Equatable {
    let peaks: WaveformPeaks?
    let peaksStart: Stamp<Source>
    let window: StampSpan<Source>
    let isMuted: Bool
    let scale: WaveformScale

    private struct Column {
        let x: Double
        let peakTop: Double
        let peakBottom: Double
        let rmsTop: Double
        let rmsBottom: Double
    }

    var body: some View {
        Canvas { context, size in
            guard let peaks, peaks.bucketCount > 0, window.duration > 0 else { return }

            let midY = size.height / 2
            let columns = self.columns(peaks: peaks, size: size, midY: midY)
            guard !columns.isEmpty else { return }

            // Two filled bands, the way Audacity draws it: a light outer envelope of the
            // extremes, and a solid inner band of RMS. Peaks alone are spiky and say little
            // about where speech actually is; the RMS body is what makes it readable.
            let colour: Color = isMuted ? .secondary : .accentColor
            context.fill(
                band(columns, top: \.peakTop, bottom: \.peakBottom, midY: midY),
                with: .color(colour.opacity(isMuted ? 0.2 : 0.45))
            )
            context.fill(
                band(columns, top: \.rmsTop, bottom: \.rmsBottom, midY: midY),
                with: .color(colour.opacity(isMuted ? 0.35 : 0.95))
            )

            var centre = Path()
            centre.move(to: CGPoint(x: 0, y: midY))
            centre.addLine(to: CGPoint(x: size.width, y: midY))
            context.stroke(centre, with: .color(colour.opacity(0.5)), lineWidth: 0.5)
        }
    }

    private func columns(peaks: WaveformPeaks, size: CGSize, midY: Double) -> [Column] {
        var result: [Column] = []
        result.reserveCapacity(Int(size.width))

        for column in 0..<Int(size.width) {
            // The axis is source time, so this is one subtraction rather than a chain of
            // clock conversions.
            let source = window.start.seconds
                + Double(column) / Double(size.width) * window.duration
            let bucket = Int((source - peaksStart.seconds) * Double(peaks.bucketsPerSecond))
            guard bucket >= 0, bucket < peaks.bucketCount, peaks.coverage[bucket] else { continue }

            let high = scale.fraction(peaks.maxima[bucket])
            let low = scale.fraction(peaks.minima[bucket])
            let loudness = scale.fraction(peaks.rms[bucket])

            result.append(Column(
                x: Double(column) + 0.5,
                peakTop: midY - midY * max(high, 0),
                peakBottom: midY - midY * min(low, 0),
                rmsTop: midY - midY * loudness,
                rmsBottom: midY + midY * loudness
            ))
        }
        return result
    }

    /// A filled ribbon: along the top edge, then back along the bottom.
    ///
    /// Every column gets at least a hairline of height so a quiet-but-present stretch still
    /// draws as a line — the difference between "silent" and "quiet" is what a cut decision
    /// turns on.
    private func band(
        _ columns: [Column],
        top: KeyPath<Column, Double>,
        bottom: KeyPath<Column, Double>,
        midY: Double
    ) -> Path {
        var path = Path()
        guard let first = columns.first else { return path }

        path.move(to: CGPoint(x: first.x, y: min(first[keyPath: top], midY - 0.25)))
        for column in columns {
            path.addLine(to: CGPoint(x: column.x, y: min(column[keyPath: top], midY - 0.25)))
        }
        for column in columns.reversed() {
            path.addLine(to: CGPoint(x: column.x, y: max(column[keyPath: bottom], midY + 0.25)))
        }
        path.closeSubpath()
        return path
    }
}
