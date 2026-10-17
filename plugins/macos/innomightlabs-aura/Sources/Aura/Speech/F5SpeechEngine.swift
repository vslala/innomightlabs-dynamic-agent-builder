import F5TTS
import Foundation

/// Speaks with F5-TTS v1 Base, running on the user's Mac through MLX.
///
/// The only place that knows which model speaks; everything else talks to `SpeechSynthesizing`.
/// The model holds roughly 2.5 GB while loaded, so it is loaded on first use and let go after a
/// few idle minutes rather than kept for the life of the app.
actor F5SpeechEngine: SpeechSynthesizing {
    private let bundleDirectory: URL
    /// How many flow steps the model takes per sentence. 32 is the PyTorch reference and sounds
    /// noticeably less synthetic than the package's own default of 16, which was listened to
    /// side by side on the same sentence; the time and the stretch/encoding that follow made no
    /// audible difference. The cost is roughly double the speaking time.
    private let steps: Int
    private var model: F5TTSModel?
    private var unloadTask: Task<Void, Never>?

    private static let idleBeforeUnloading: Duration = .seconds(300)

    init(bundleDirectory: URL, steps: Int = 32) {
        self.bundleDirectory = bundleDirectory
        self.steps = steps
    }

    func synthesize(sentence: String, voice: VoiceSample) async throws -> [Float] {
        unloadTask?.cancel()
        defer { scheduleUnload() }

        let model = try await loadedModel()
        // A fixed seed: the same text in the same voice comes out the same, so a clip that has
        // to be made again (a copied session, a cleared cache) matches the one it replaces.
        return try await model.generate(
            text: sentence,
            referenceAudio: voice.audioURL,
            referenceText: voice.text,
            options: try F5TTSSynthesisOptions(steps: steps, seed: 1)
        )
    }

    private func loadedModel() async throws -> F5TTSModel {
        if let model, model.isLoaded { return model }
        let loaded = try await F5TTSModel.fromBundle(bundleDirectory)
        model = loaded
        return loaded
    }

    private func scheduleUnload() {
        unloadTask = Task { [weak self] in
            try? await Task.sleep(for: Self.idleBeforeUnloading)
            guard !Task.isCancelled else { return }
            await self?.unload()
        }
    }

    private func unload() {
        model?.unload()
        model = nil
    }
}
