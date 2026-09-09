import AVFoundation

/// Converts an arbitrary input format to mono float32 at a target sample rate (16kHz
/// for the wake-word pipeline), in AVAudioEngine's standard normalized `[-1, 1]` range.
/// Callers that need the wake-word models' unusual int16-range-preserving scale
/// (`x * 32768`) apply that themselves — this type only handles format conversion.
final class AudioResampler {
    private let converter: AVAudioConverter
    let outputFormat: AVAudioFormat

    init?(inputFormat: AVAudioFormat, sampleRate: Double = 16_000) {
        guard let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: sampleRate,
            channels: 1,
            interleaved: false
        ), let converter = AVAudioConverter(from: inputFormat, to: targetFormat) else {
            return nil
        }
        self.converter = converter
        self.outputFormat = targetFormat
    }

    func resample(_ buffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        let ratio = outputFormat.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 16
        guard let outputBuffer = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else {
            return nil
        }

        var error: NSError?
        var consumed = false
        converter.convert(to: outputBuffer, error: &error) { _, outStatus in
            if consumed {
                outStatus.pointee = .noDataNow
                return nil
            }
            consumed = true
            outStatus.pointee = .haveData
            return buffer
        }

        return error == nil ? outputBuffer : nil
    }
}
