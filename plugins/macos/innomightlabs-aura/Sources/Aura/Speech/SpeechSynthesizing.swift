import Foundation

/// A recording of the speaker, with what is said in it, that the model learns their voice from.
struct VoiceSample: Equatable, Sendable {
    let audioURL: URL
    let text: String
}

/// Turns a sentence into speech in a given voice.
///
/// The seam between Aura and whichever model does the speaking. `F5SpeechEngine` is the real one;
/// tests substitute their own. Everything above this — splitting, fitting, writing the clip,
/// placing it on the timeline — works the same whatever speaks.
protocol SpeechSynthesizing: Sendable {
    /// One sentence, spoken at the voice's natural pace.
    /// - Returns: mono samples at `SpeechAudio.sampleRate`.
    func synthesize(sentence: String, voice: VoiceSample) async throws -> [Float]
}

enum SpeechAudio {
    /// What the speech model produces, and so what every replacement clip is stored at.
    static let sampleRate: Double = 24_000
}
