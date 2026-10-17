import AVFoundation
import CryptoKit
import Foundation

/// Where a line of narration belongs in a demo.
enum NarrationSlot: Hashable, Sendable {
    case intro
    case step(String)
    case outro
}

struct NarrationItem: Equatable, Sendable {
    let slot: NarrationSlot
    let text: String
}

/// What to say in a demo, in the order it is said. Pure.
enum NarrationPlan {
    static func items(for spec: DemoSpec) -> [NarrationItem] {
        func item(_ slot: NarrationSlot, _ text: String?) -> NarrationItem? {
            let trimmed = text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return trimmed.isEmpty ? nil : NarrationItem(slot: slot, text: trimmed)
        }
        let steps = spec.steps.compactMap { step -> NarrationItem? in
            // A handover hands the browser to the user, who is not listening to a script.
            if case .handover = step.action { return nil }
            return item(.step(step.id), step.narration)
        }
        return [item(.intro, spec.intro)].compactMap { $0 } + steps + [item(.outro, spec.outro)].compactMap { $0 }
    }
}

/// A line spoken before the take, ready to be played at the right moment.
struct NarrationClip: Equatable, Sendable {
    let text: String
    let url: URL
    let duration: TimeInterval
}

/// Every clip a take needs, made before it starts so the take can wait for each one.
struct NarrationTrack: Equatable, Sendable {
    var clips: [NarrationSlot: NarrationClip]

    var isEmpty: Bool { clips.isEmpty }
}

/// The beats of a narrated take. Constants rather than options: they are what makes a take feel
/// paced, and a user has no way to judge them before watching one.
enum NarrationTiming {
    /// Quiet before the first and after the last line, so the video neither starts mid-motion nor
    /// stops mid-sentence.
    static let edgeHold: TimeInterval = 1.0
    /// How far into its line a step's action begins: the viewer hears "click New agent" just before
    /// the click, not after it.
    static let actionLead: TimeInterval = 0.6
    /// Settle time after a step before the next begins.
    static let gap: TimeInterval = 0.4

    /// How much longer a step must wait, once its action is done, for its line to finish.
    static func remainingHold(clip: TimeInterval, elapsed: TimeInterval) -> TimeInterval {
        max(0, clip - max(0, elapsed))
    }
}

/// Speaks every item once and keeps the clips, so retaking a demo whose text has not changed does
/// not speak it again.
enum NarrationRenderer {
    enum RenderError: Error, LocalizedError {
        case unreadableClip
        var errorDescription: String? { "A narration clip could not be read back." }
    }

    /// - Parameters:
    ///   - voiceID: names the voice in the cache key, so changing it speaks everything again.
    ///   - directory: the cache. Derived data, safe to delete.
    ///   - progress: items finished, out of `items.count`.
    static func render(
        _ items: [NarrationItem],
        voice: VoiceSample,
        voiceID: String,
        using synthesizer: any SpeechSynthesizing,
        cacheDirectory directory: URL,
        progress: @Sendable (Int) -> Void = { _ in }
    ) async throws -> NarrationTrack {
        var clips: [NarrationSlot: NarrationClip] = [:]
        for (index, item) in items.enumerated() {
            try Task.checkCancellation()
            let url = directory.appendingPathComponent(cacheKey(text: item.text, voiceID: voiceID)).appendingPathExtension("m4a")
            if !FileManager.default.fileExists(atPath: url.path) {
                let spoken = try await SpeechReplacementRenderer.speakNaturally(text: item.text, voice: voice, using: synthesizer)
                try SpeechReplacementRenderer.write(spoken, to: url)
            }
            clips[item.slot] = NarrationClip(text: item.text, url: url, duration: try duration(of: url))
            progress(index + 1)
        }
        return NarrationTrack(clips: clips)
    }

    /// Bump when synthesis or clip processing changes; old clips remain untouched on disk.
    static let cacheVersion = "narration-v2"

    static func cacheKey(text: String, voiceID: String) -> String {
        SHA256.hash(data: Data((cacheVersion + "\n" + voiceID + "\n" + text).utf8))
            .prefix(16).map { String(format: "%02x", $0) }.joined()
    }

    static func duration(of url: URL) throws -> TimeInterval {
        let file = try AVAudioFile(forReading: url)
        guard file.processingFormat.sampleRate > 0, file.length > 0 else { throw RenderError.unreadableClip }
        return Double(file.length) / file.processingFormat.sampleRate
    }
}
