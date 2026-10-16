import AVFoundation
import Foundation

/// Writes a denoised copy of an audio file.
///
/// The recording is never touched: the result is a derived file the composition plays in the
/// original's place, so turning Studio Sound off is just not using it. Same length, same
/// sample rate and channel count as the source, which is what lets it stand in for the
/// original without anything on the timeline moving.
enum StudioSoundRenderer {
    /// Frames read per pass. Small enough to stay light on memory for an hour-long recording,
    /// large enough that the per-pass overhead is nothing.
    private static let chunkFrames: AVAudioFrameCount = 32_768

    /// - Parameter progress: fraction complete, 0...1. Called from the rendering task.
    /// - Throws: `CancellationError` if the task is cancelled; nothing is left at `destination`
    ///   in that case, or on any other failure.
    static func render(
        source: URL,
        to destination: URL,
        options: SpectralDenoiser.Options = .default,
        progress: @Sendable (Double) -> Void = { _ in }
    ) async throws {
        let input = try AVAudioFile(forReading: source)
        let format = input.processingFormat
        let channels = Int(format.channelCount)

        // Written beside the destination and moved into place at the end, so a cancelled or
        // failed render can never leave a half-written file that looks like a finished one.
        let partial = destination.deletingLastPathComponent()
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("m4a")
        defer { try? FileManager.default.removeItem(at: partial) }

        // The scope ends the file's life, which is what finalizes it — `AVAudioFile` has no
        // close(); it is complete once released, and must be before it is moved.
        do {
            let output = try AVAudioFile(
                forWriting: partial,
                settings: [
                    AVFormatIDKey: kAudioFormatMPEG4AAC,
                    AVSampleRateKey: format.sampleRate,
                    AVNumberOfChannelsKey: channels,
                    AVEncoderBitRateKey: 96_000 * channels
                ],
                commonFormat: .pcmFormatFloat32,
                interleaved: false
            )

            var denoisers = (0..<channels).map { _ in SpectralDenoiser(sampleRate: format.sampleRate, options: options) }
            let total = max(1, input.length)

            while input.framePosition < input.length {
                try Task.checkCancellation()
                guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: chunkFrames) else { break }
                try input.read(into: buffer)
                guard buffer.frameLength > 0 else { break }

                let cleaned = (0..<channels).map { channel in
                    denoisers[channel].process(samples(of: buffer, channel: channel))
                }
                try write(cleaned, format: format, to: output)
                progress(Double(input.framePosition) / Double(total))
            }

            try write((0..<channels).map { denoisers[$0].finish() }, format: format, to: output)
        }

        try? FileManager.default.removeItem(at: destination)
        try FileManager.default.moveItem(at: partial, to: destination)
        progress(1)
    }

    private static func samples(of buffer: AVAudioPCMBuffer, channel: Int) -> [Float] {
        Array(UnsafeBufferPointer(start: buffer.floatChannelData![channel], count: Int(buffer.frameLength)))
    }

    private static func write(_ channels: [[Float]], format: AVAudioFormat, to file: AVAudioFile) throws {
        let frames = channels.first?.count ?? 0
        guard frames > 0, let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames)) else {
            return
        }
        buffer.frameLength = AVAudioFrameCount(frames)
        for (index, samples) in channels.enumerated() {
            samples.withUnsafeBufferPointer {
                buffer.floatChannelData![index].update(from: $0.baseAddress!, count: frames)
            }
        }
        try file.write(from: buffer)
    }
}
