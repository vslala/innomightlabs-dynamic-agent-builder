import AVFoundation
import SwiftUI

@main
struct AuraApp: App {
    @StateObject private var recordingController: RecordingController
    /// Held by the app, not by a view: review windows outlive the menu that opened them, and
    /// the menu's content view does not exist most of the time.
    private let reviewWindows = ReviewWindowPresenter()

    // Behind `FeatureFlags.isWakeWordListenerEnabled` and off by default — see there for why.
    // Still the Stage 2 manual-verification wiring: detections only reach a debug log, so
    // this is a diagnostic harness rather than a feature. Lazily built, so with the flag off
    // the CoreML models are never even loaded.
    private static let wakeWordListener: WakeWordListener? = {
        guard
            let resourcesURL = Bundle.main.resourceURL,
            let melspectrogram = try? Melspectrogram(resourcesURL: resourcesURL),
            let embeddingURL = Bundle.main.url(forResource: "embedding_model", withExtension: "mlmodelc"),
            let embedding = try? CoreMLStageModel(modelURL: embeddingURL, inputName: "input", inputShape: [1, 76, 32, 1]),
            let classifierURL = Bundle.main.url(forResource: "hey_mycroft_v0.1", withExtension: "mlmodelc"),
            let classifier = try? CoreMLStageModel(modelURL: classifierURL, inputName: "input", inputShape: [1, 16, 96])
        else { return nil }

        let pipeline = WakeWordFeaturePipeline(melspectrogram: melspectrogram, embedding: embedding, classifier: classifier)
        let listener = WakeWordListener(pipeline: pipeline)
        listener.onDetection = { debugLog("WAKE WORD DETECTED") }
        listener.onScore = { score in debugLog("score=\(score)") }
        return listener
    }()

    private static func debugLog(_ message: String) {
        let line = "[\(Date())] \(message)\n"
        print(line)
        guard let data = line.data(using: .utf8) else { return }
        let url = URL(fileURLWithPath: "/tmp/aura-debug.log")
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        if let handle = try? FileHandle(forWritingTo: url) {
            handle.seekToEndOfFile()
            handle.write(data)
            try? handle.close()
        }
    }

    init() {
        let controller = RecordingController()
        let presenter = reviewWindows
        controller.onSessionCompleted = { folder in presenter.open(folder) }
        _recordingController = StateObject(wrappedValue: controller)

        // No microphone permission prompt and no listener unless the flag is on: with it off,
        // Aura touches the microphone only while actually recording.
        guard FeatureFlags.isWakeWordListenerEnabled else { return }
        Task {
            guard await AVCaptureDevice.requestAccess(for: .audio) else { return }
            try? Self.wakeWordListener?.start()
        }
    }

    var body: some Scene {
        MenuBarExtra("Aura", systemImage: "waveform") {
            MenuBarContentView(controller: recordingController, reviewWindows: reviewWindows)
        }
    }
}
