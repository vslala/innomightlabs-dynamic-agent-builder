import AVFoundation
import Foundation

/// Speech made from text, fitted to a selection, before it is written as a clip.
struct SpokenText: Sendable {
    fileprivate let samples: [Float]
    /// How the speech meets the selection: stretched, padded, or the picture held.
    let fit: DurationFit
    let sentenceCount: Int
}

enum SpeechRenderError: Error, Equatable, LocalizedError {
    case nothingToSay

    var errorDescription: String? {
        switch self {
        case .nothingToSay: return "There is no text to speak."
        }
    }
}

/// Makes the clip that replaces a selection, in two steps so the user can be asked about a long
/// hold before anything is written.
///
/// `speak` is the slow part (one model call per sentence); `write` is quick. A replacement is
/// applied to the document only after `write` succeeds, so the edit never describes audio that
/// does not exist.
enum SpeechReplacementRenderer {
    /// Silence between sentences, which the model does not produce on its own.
    static let gapBetweenSentences: TimeInterval = 0.25
    /// Fades at both ends of every clip, so splicing it in cannot click.
    private static let edgeFade: TimeInterval = 0.008

    /// - Parameters:
    ///   - selection: how long the words being replaced last, which the speech is fitted to.
    ///   - progress: fraction of sentences spoken, 0...1.
    static func speak(
        text: String,
        selection: TimeInterval,
        voice: VoiceSample,
        using synthesizer: any SpeechSynthesizing,
        progress: @Sendable (Double) -> Void = { _ in }
    ) async throws -> SpokenText {
        let sentences = SentenceSplitter.split(text)
        guard !sentences.isEmpty else { throw SpeechRenderError.nothingToSay }

        let rate = SpeechAudio.sampleRate
        let gap = [Float](repeating: 0, count: Int(gapBetweenSentences * rate))

        var joined: [Float] = []
        for (index, sentence) in sentences.enumerated() {
            try Task.checkCancellation()
            if index > 0 { joined += gap }
            joined += try await synthesizer.synthesize(sentence: sentence, voice: voice)
            progress(Double(index + 1) / Double(sentences.count))
        }

        let fit = DurationFitter.fit(speech: Double(joined.count) / rate, selection: selection)
        return SpokenText(samples: fitted(joined, to: fit, selection: selection), fit: fit, sentenceCount: sentences.count)
    }

    /// Speech at the pace the voice naturally has, with nothing to fit it to. For narration, which
    /// has no selection: the take is paced to the clip, not the clip to the take.
    static func speakNaturally(
        text: String,
        voice: VoiceSample,
        using synthesizer: any SpeechSynthesizing,
        progress: @Sendable (Double) -> Void = { _ in }
    ) async throws -> SpokenText {
        let sentences = SentenceSplitter.split(text)
        guard !sentences.isEmpty else { throw SpeechRenderError.nothingToSay }

        let rate = SpeechAudio.sampleRate
        let gap = [Float](repeating: 0, count: Int(gapBetweenSentences * rate))
        var joined: [Float] = []
        for (index, sentence) in sentences.enumerated() {
            try Task.checkCancellation()
            if index > 0 { joined += gap }
            joined += try await synthesizer.synthesize(sentence: sentence, voice: voice)
            progress(Double(index + 1) / Double(sentences.count))
        }
        let duration = Double(joined.count) / rate
        return SpokenText(
            samples: joined,
            fit: DurationFit(action: .hold, clipDuration: duration, hold: 0),
            sentenceCount: sentences.count
        )
    }

    /// Writes the clip. Atomic: a cancelled or failed write leaves nothing at `destination`.
    /// - Returns: the clip's length, which is what the document stores.
    @discardableResult
    static func write(_ spoken: SpokenText, to destination: URL) throws -> TimeInterval {
        let rate = SpeechAudio.sampleRate
        var samples = spoken.samples
        applyEdgeFades(to: &samples, rate: rate)

        try FileManager.default.createDirectory(
            at: destination.deletingLastPathComponent(), withIntermediateDirectories: true
        )
        let partial = destination.deletingLastPathComponent()
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("m4a")
        defer { try? FileManager.default.removeItem(at: partial) }

        // The scope ends the file's life, which finalizes it — `AVAudioFile` has no close().
        do {
            let file = try AVAudioFile(forWriting: partial, settings: [
                AVFormatIDKey: kAudioFormatMPEG4AAC,
                AVSampleRateKey: rate,
                AVNumberOfChannelsKey: 1,
                AVEncoderBitRateKey: 64_000
            ], commonFormat: .pcmFormatFloat32, interleaved: false)

            let format = file.processingFormat
            let chunk = 32_768
            var position = 0
            while position < samples.count {
                let count = min(chunk, samples.count - position)
                let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(count))!
                buffer.frameLength = AVAudioFrameCount(count)
                samples[position..<(position + count)].withUnsafeBufferPointer {
                    buffer.floatChannelData![0].update(from: $0.baseAddress!, count: count)
                }
                try file.write(from: buffer)
                position += count
            }
        }

        try? FileManager.default.removeItem(at: destination)
        try FileManager.default.moveItem(at: partial, to: destination)
        return Double(samples.count) / rate
    }

    // MARK: - Fitting

    private static func fitted(_ samples: [Float], to fit: DurationFit, selection: TimeInterval) -> [Float] {
        let target = Int((fit.clipDuration * SpeechAudio.sampleRate).rounded())
        switch fit.action {
        case .stretch(let tempo):
            // Stretching lands within a few samples; trimmed or padded so the clip is exactly
            // the selection's length and the timeline never drifts by a rounding error.
            return exactly(TimeStretcher.stretch(samples, tempo: tempo, sampleRate: SpeechAudio.sampleRate), count: target)
        case .pad:
            return exactly(samples, count: target)
        case .hold:
            return samples
        }
    }

    private static func exactly(_ samples: [Float], count: Int) -> [Float] {
        if samples.count >= count { return Array(samples.prefix(count)) }
        return samples + [Float](repeating: 0, count: count - samples.count)
    }

    private static func applyEdgeFades(to samples: inout [Float], rate: Double) {
        let length = min(Int(edgeFade * rate), samples.count / 2)
        guard length > 0 else { return }
        for index in 0..<length {
            let gain = Float(index) / Float(length)
            samples[index] *= gain
            samples[samples.count - 1 - index] *= gain
        }
    }
}
