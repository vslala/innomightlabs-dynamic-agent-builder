import Foundation

/// Which voice narrates browser demos. One place, because the take, the script preview and the
/// review window's rewrites must all use the same one or a demo would change voice mid-sentence.
///
/// Only the macOS voices today: the cloning model learns from the user's own recording, and a
/// browser take has no microphone to learn from. `SpeechSynthesizing` is the seam where it would
/// plug in.
enum NarrationVoice {
    private static let identifierKey = "Aura.narrationVoiceIdentifier"

    /// Nil means the best installed voice for the user's language.
    static var identifier: String? {
        get { UserDefaults.standard.string(forKey: identifierKey) }
        set { UserDefaults.standard.set(newValue, forKey: identifierKey) }
    }

    /// Snapshot the actual voice once, including fallback when a saved voice is no longer installed.
    static func resolve() throws -> (cacheID: String, synthesizer: SystemSpeechSynthesizer) {
        let synthesizer = try SystemSpeechSynthesizer(voiceIdentifier: identifier)
        return ("system:\(synthesizer.voiceIdentifier)", synthesizer)
    }

    /// The system voices ignore the reference; `SpeechSynthesizing` is shaped for the cloning model.
    static let reference = VoiceSample(audioURL: URL(fileURLWithPath: "/dev/null"), text: "")
}
