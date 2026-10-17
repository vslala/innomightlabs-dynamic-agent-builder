import AVFoundation
import Foundation

/// Speaks with the voices macOS ships, on the device, with nothing to download.
///
/// The narration voice every Mac has. It ignores `VoiceSample`: those voices cannot learn one, so
/// the argument exists only because `SpeechSynthesizing` is shaped for the cloning model.
final class SystemSpeechSynthesizer: SpeechSynthesizing, @unchecked Sendable {
    enum SynthesisError: Error, LocalizedError {
        case noVoice
        case unreadableAudio
        case mismatchedAudioFormats

        var errorDescription: String? {
            switch self {
            case .noVoice: return "macOS has no voice to speak with. Add one in System Settings → Accessibility → Spoken Content."
            case .unreadableAudio: return "The voice produced audio Aura could not read."
            case .mismatchedAudioFormats: return "The voice changed audio format while speaking. Try another voice."
            }
        }
    }

    /// Plain descriptions keep voice selection testable without installed speech assets.
    struct VoiceDescription: Equatable {
        let identifier: String
        let name: String
        let language: String
        let quality: Int
        let isNovelty: Bool
    }

    private let resolvedVoice: AVSpeechSynthesisVoice
    var voiceIdentifier: String { resolvedVoice.identifier }

    /// Resolve once, so every sentence and its cache identity use the same actual voice.
    init(voiceIdentifier: String? = nil) throws {
        let installed = AVSpeechSynthesisVoice.speechVoices()
        let systemDefault = AVSpeechSynthesisVoice(language: nil)
        let voices = installed + [systemDefault].compactMap { $0 }
        guard let identifier = Self.selectedIdentifier(
            requested: voiceIdentifier, voices: voices.map(Self.describe),
            locale: Locale.current.identifier, defaultIdentifier: systemDefault?.identifier
        ), let resolved = voices.first(where: { $0.identifier == identifier }) else {
            throw SynthesisError.noVoice
        }
        resolvedVoice = resolved
    }

    private static func describe(_ voice: AVSpeechSynthesisVoice) -> VoiceDescription {
        VoiceDescription(identifier: voice.identifier, name: voice.name, language: voice.language,
                         quality: voice.quality.rawValue, isNovelty: voice.voiceTraits.contains(.isNoveltyVoice))
    }

    /// Novelty voices stay out of the narration picker; an existing explicit selection still works.
    static func availableVoices(language: String = Locale.current.language.languageCode?.identifier ?? "en") -> [AVSpeechSynthesisVoice] {
        let installed = AVSpeechSynthesisVoice.speechVoices()
        let ranked = rankedVoices(installed.map(describe), language: language, locale: Locale.current.identifier,
                                  defaultIdentifier: AVSpeechSynthesisVoice(language: nil)?.identifier)
        return ranked.compactMap { description in installed.first { $0.identifier == description.identifier } }
    }

    static func rankedVoices(
        _ voices: [VoiceDescription], language: String, locale: String, defaultIdentifier: String?
    ) -> [VoiceDescription] {
        func normalized(_ value: String) -> String { value.replacingOccurrences(of: "_", with: "-").lowercased() }
        let language = normalized(language).split(separator: "-").first.map(String.init) ?? "en"
        let sorted = voices.filter {
            !$0.isNovelty && normalized($0.language).split(separator: "-").first.map(String.init) == language
        }.sorted { a, b in
            if a.quality != b.quality { return a.quality > b.quality }
            let aLocal = normalized(a.language) == normalized(locale)
            let bLocal = normalized(b.language) == normalized(locale)
            if aLocal != bLocal { return aLocal }
            let aDefault = a.identifier == defaultIdentifier
            let bDefault = b.identifier == defaultIdentifier
            if aDefault != bDefault { return aDefault }
            if a.name != b.name { return a.name < b.name }
            if a.language != b.language { return a.language < b.language }
            return a.identifier < b.identifier
        }
        var seen: Set<String> = []
        return sorted.filter { seen.insert($0.identifier).inserted }
    }

    static func selectedIdentifier(
        requested: String?, voices: [VoiceDescription], locale: String, defaultIdentifier: String?
    ) -> String? {
        if let requested, voices.contains(where: { $0.identifier == requested }) { return requested }
        return rankedVoices(voices, language: locale, locale: locale, defaultIdentifier: defaultIdentifier).first?.identifier
            ?? voices.first(where: { $0.identifier == defaultIdentifier && !$0.isNovelty })?.identifier
    }

    func synthesize(sentence: String, voice: VoiceSample) async throws -> [Float] {
        let utterance = AVSpeechUtterance(string: sentence)
        utterance.voice = resolvedVoice
        return try await Self.speak(utterance)
    }

    /// `write` hands over audio as it is made and signals the end with an empty buffer. The
    /// buffers are joined and converted once at the end, so only plain samples cross back out.
    @MainActor
    private static func speak(_ utterance: AVSpeechUtterance) async throws -> [Float] {
        try await withCheckedThrowingContinuation { continuation in
            let synthesizer = AVSpeechSynthesizer()
            nonisolated(unsafe) var buffers: [AVAudioPCMBuffer] = []
            nonisolated(unsafe) var finished = false
            synthesizer.write(utterance) { buffer in
                guard !finished, let pcm = buffer as? AVAudioPCMBuffer else { return }
                if pcm.frameLength == 0 {
                    finished = true
                    // Keeps the synthesizer alive until it has finished writing.
                    _ = synthesizer
                    continuation.resume(with: Result { try samples(from: buffers) })
                } else {
                    buffers.append(pcm)
                }
            }
        }
    }

    /// Joins the buffers and converts them once, to mono Float32 at the speech model's rate, so a
    /// sample-rate converter never restarts mid-sentence.
    static func samples(from buffers: [AVAudioPCMBuffer]) throws -> [Float] {
        guard let first = buffers.first else { return [] }
        let format = first.format
        guard buffers.allSatisfy({ $0.format == format }) else { throw SynthesisError.mismatchedAudioFormats }
        // The channel-pointer copy below is planar; interleaved multichannel PCM needs a different copy.
        guard !format.isInterleaved || format.channelCount == 1 else { throw SynthesisError.unreadableAudio }
        let frames = buffers.reduce(0) { $0 + Int($1.frameLength) }
        guard let joined = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames)) else {
            throw SynthesisError.unreadableAudio
        }
        var offset = 0
        for buffer in buffers {
            let count = Int(buffer.frameLength)
            for channel in 0..<Int(format.channelCount) {
                if let source = buffer.floatChannelData?[channel], let target = joined.floatChannelData?[channel] {
                    (target + offset).update(from: source, count: count)
                } else if let source = buffer.int16ChannelData?[channel], let target = joined.int16ChannelData?[channel] {
                    (target + offset).update(from: source, count: count)
                } else {
                    throw SynthesisError.unreadableAudio
                }
            }
            offset += count
        }
        joined.frameLength = AVAudioFrameCount(offset)

        guard let output = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: SpeechAudio.sampleRate, channels: 1, interleaved: false),
              let converter = AVAudioConverter(from: format, to: output),
              let converted = AVAudioPCMBuffer(
                pcmFormat: output,
                frameCapacity: AVAudioFrameCount(Double(offset) * SpeechAudio.sampleRate / format.sampleRate) + 1_024
              ) else { throw SynthesisError.unreadableAudio }

        var supplied = false
        var failure: NSError?
        let status = converter.convert(to: converted, error: &failure) { _, inputStatus in
            if supplied {
                inputStatus.pointee = .endOfStream
                return nil
            }
            supplied = true
            inputStatus.pointee = .haveData
            return joined
        }
        guard status != .error, let data = converted.floatChannelData?[0] else { throw failure ?? SynthesisError.unreadableAudio }
        return Array(UnsafeBufferPointer(start: data, count: Int(converted.frameLength)))
    }
}
