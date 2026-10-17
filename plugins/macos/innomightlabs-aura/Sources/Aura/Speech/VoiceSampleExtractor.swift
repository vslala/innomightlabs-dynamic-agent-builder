import AVFoundation
import Foundation

/// Cuts a reference clip out of a recording in the form the speech model wants: mono, 24 kHz.
enum VoiceSampleExtractor {
    enum ExtractionError: Error, LocalizedError {
        case unreadable
        case outsideRecording

        var errorDescription: String? {
            switch self {
            case .unreadable: return "The voice recording could not be read to learn your voice from."
            case .outsideRecording: return "The chosen stretch of voice is outside the recording."
            }
        }
    }

    /// - Parameter range: seconds into `source`'s own timeline.
    /// - Returns: what the clip says, paired with the file it was written to.
    static func extract(
        _ reference: VoiceReference,
        from source: URL,
        to destination: URL
    ) throws -> VoiceSample {
        let input = try AVAudioFile(forReading: source)
        let inputFormat = input.processingFormat
        guard let outputFormat = AVAudioFormat(
            commonFormat: .pcmFormatFloat32, sampleRate: SpeechAudio.sampleRate, channels: 1, interleaved: false
        ), let converter = AVAudioConverter(from: inputFormat, to: outputFormat) else {
            throw ExtractionError.unreadable
        }

        let startFrame = AVAudioFramePosition(reference.start * inputFormat.sampleRate)
        let frames = AVAudioFrameCount(reference.duration * inputFormat.sampleRate)
        guard startFrame >= 0, startFrame + AVAudioFramePosition(frames) <= input.length else {
            throw ExtractionError.outsideRecording
        }

        input.framePosition = startFrame
        guard let chunk = AVAudioPCMBuffer(pcmFormat: inputFormat, frameCapacity: frames) else {
            throw ExtractionError.unreadable
        }
        try input.read(into: chunk, frameCount: frames)

        let capacity = AVAudioFrameCount(reference.duration * SpeechAudio.sampleRate) + 1_024
        guard let converted = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else {
            throw ExtractionError.unreadable
        }
        var supplied = false
        var conversionError: NSError?
        let status = converter.convert(to: converted, error: &conversionError) { _, inputStatus in
            if supplied {
                inputStatus.pointee = .endOfStream
                return nil
            }
            supplied = true
            inputStatus.pointee = .haveData
            return chunk
        }
        guard status != .error, converted.frameLength > 0 else { throw conversionError ?? ExtractionError.unreadable }

        try FileManager.default.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? FileManager.default.removeItem(at: destination)
        let output = try AVAudioFile(
            forWriting: destination,
            settings: [
                AVFormatIDKey: kAudioFormatLinearPCM,
                AVSampleRateKey: SpeechAudio.sampleRate,
                AVNumberOfChannelsKey: 1,
                AVLinearPCMBitDepthKey: 16,
                AVLinearPCMIsFloatKey: false
            ],
            commonFormat: .pcmFormatFloat32,
            interleaved: false
        )
        try output.write(from: converted)

        return VoiceSample(audioURL: destination, text: reference.text)
    }
}
