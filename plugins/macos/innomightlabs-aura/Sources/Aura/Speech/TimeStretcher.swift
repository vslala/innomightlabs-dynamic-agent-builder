import Foundation

/// Speeds up or slows down speech without changing its pitch.
///
/// Waveform-similarity overlap-add: short windows are copied out at one rate and laid down at
/// another, each nudged to the offset where it lines up best with what is already there, so the
/// joins do not buzz. Written out in plain Swift because the alternative, an offline
/// `AVAudioEngine` graph, is far more machinery than a ±15% nudge on a few seconds of speech
/// deserves.
enum TimeStretcher {
    /// - Parameter tempo: output length is the input's divided by this. 1.1 is 10% faster.
    static func stretch(_ samples: [Float], tempo: Double, sampleRate: Double = 24_000) -> [Float] {
        guard tempo.isFinite, tempo > 0, abs(tempo - 1) > 0.001, samples.count > 512 else { return samples }

        let window = Int(sampleRate * 0.030)          // 30 ms
        let hop = window / 2                           // synthesis hop: 50% overlap
        let search = Int(sampleRate * 0.010)           // look ±10 ms for the best alignment
        let analysisHop = Double(hop) * tempo

        let outputLength = Int(Double(samples.count) / tempo)
        var output = [Float](repeating: 0, count: outputLength + window)
        var weight = [Float](repeating: 0, count: outputLength + window)
        let fade = (0..<window).map { Float(0.5 - 0.5 * cos(2 * Double.pi * Double($0) / Double(window))) }

        var previousTail: [Float]?
        var outputPosition = 0
        var step = 0

        while outputPosition < outputLength {
            var start = Int(Double(step) * analysisHop)
            guard start + window < samples.count else { break }

            if let tail = previousTail {
                // Slide the next window to where it best continues the previous one.
                var bestOffset = 0
                var bestScore = -Float.infinity
                for offset in stride(from: -search, through: search, by: 4) {
                    let candidate = start + offset
                    guard candidate >= 0, candidate + window <= samples.count else { continue }
                    var score: Float = 0
                    for index in stride(from: 0, to: tail.count, by: 2) {
                        score += tail[index] * samples[candidate + index]
                    }
                    if score > bestScore { bestScore = score; bestOffset = offset }
                }
                start += bestOffset
            }

            for index in 0..<window where outputPosition + index < output.count {
                output[outputPosition + index] += samples[start + index] * fade[index]
                weight[outputPosition + index] += fade[index]
            }
            // What the next window should continue from: this window's natural successor.
            let successor = start + hop
            previousTail = successor + hop <= samples.count ? Array(samples[successor..<(successor + hop)]) : nil

            outputPosition += hop
            step += 1
        }

        for index in 0..<outputLength where weight[index] > 0.0001 {
            output[index] /= weight[index]
        }
        return Array(output.prefix(outputLength))
    }
}
