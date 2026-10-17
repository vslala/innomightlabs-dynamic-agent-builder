import AVFoundation
import XCTest
@testable import Aura

/// Runs the real model end to end: the installer downloads and verifies the pinned bundle, the
/// engine loads it, and a sentence is spoken in a real recording of the speaker.
///
/// Skipped unless `AURA_REAL_VOICE_DIR` names a folder to keep the ~700 MB download in (so it is
/// fetched once, not on every run) holding `voice.wav` (a 5–10 s mono 24 kHz clip) and
/// `voice.txt` (what it says):
///
///     TEST_RUNNER_AURA_REAL_VOICE_DIR=~/aura-real-voice xcodebuild … test -only-testing:AuraTests/RealVoiceTests
@MainActor
final class RealVoiceTests: XCTestCase {
    func testTheRealModelSpeaksASentenceInTheReferenceVoice() async throws {
        guard let value = ProcessInfo.processInfo.environment["AURA_REAL_VOICE_DIR"] else {
            throw XCTSkip("Set AURA_REAL_VOICE_DIR to run the real model (about 700 MB the first time).")
        }
        let path = NSString(string: value).expandingTildeInPath
        let directory = URL(fileURLWithPath: path, isDirectory: true)
        let voice = VoiceSample(
            audioURL: directory.appendingPathComponent("voice.wav"),
            text: try String(contentsOf: directory.appendingPathComponent("voice.txt"), encoding: .utf8)
                .trimmingCharacters(in: .whitespacesAndNewlines)
        )

        let defaults = UserDefaults(suiteName: "aura-real-voice-\(UUID().uuidString)")!
        let installer = SpeechEngineInstaller(
            engineDirectory: directory.appendingPathComponent("engine"), defaults: defaults
        )

        if !installer.isReady {
            installer.beginEnabling()
            XCTAssertEqual(installer.state, .awaitingLicence)
            installer.acceptLicence()
            let start = Date()
            while case .installing(let fraction) = installer.state {
                if Int(Date().timeIntervalSince(start)) % 10 == 0 { print("download \(Int(fraction * 100))%") }
                try await Task.sleep(for: .seconds(1))
                if Date().timeIntervalSince(start) > 1_500 { return XCTFail("download took too long") }
            }
            print("download finished in \(Int(Date().timeIntervalSince(start)))s")
        }
        XCTAssertEqual(installer.state, .ready, "every file matched the checksum pinned in SpeechModelBundle")

        let engine = F5SpeechEngine(bundleDirectory: installer.modelDirectory)
        let text = "I will serve as a support chatbot on your site or a helper or something like that."

        let started = Date()
        let spoken = try await SpeechReplacementRenderer.speak(text: text, selection: 6.46, voice: voice, using: engine)
        let took = Date().timeIntervalSince(started)

        let clip = directory.appendingPathComponent("out/real-voice.m4a")
        let duration = try SpeechReplacementRenderer.write(spoken, to: clip)
        print("spoke \(text.count) characters: clip \(String(format: "%.2f", duration))s, "
              + "fit \(spoken.fit.action), took \(String(format: "%.1f", took))s (first call, model loading included)")

        XCTAssertGreaterThan(duration, 3)
        XCTAssertTrue(FileManager.default.fileExists(atPath: clip.path))

        // A second sentence, once the model is warm, is the speed a user will actually feel.
        let again = Date()
        _ = try await engine.synthesize(sentence: "And that is why I started building it.", voice: voice)
        print("second sentence took \(String(format: "%.1f", Date().timeIntervalSince(again)))s")
    }

    /// Writes the same sentence several ways, each changing one thing, so a person can hear which
    /// change is responsible for a problem. Not an assertion test: the output is for listening.
    func testWritesVariantsForListening() async throws {
        guard let value = ProcessInfo.processInfo.environment["AURA_REAL_VOICE_DIR"] else {
            throw XCTSkip("Set AURA_REAL_VOICE_DIR to run the real model.")
        }
        let directory = URL(fileURLWithPath: NSString(string: value).expandingTildeInPath, isDirectory: true)
        let voice = VoiceSample(
            audioURL: directory.appendingPathComponent("voice.wav"),
            text: try String(contentsOf: directory.appendingPathComponent("voice.txt"), encoding: .utf8)
                .trimmingCharacters(in: .whitespacesAndNewlines)
        )
        let installer = SpeechEngineInstaller(
            engineDirectory: directory.appendingPathComponent("engine"),
            defaults: UserDefaults(suiteName: "aura-variants-\(UUID().uuidString)")!
        )
        if !installer.isReady {
            installer.beginEnabling()
            installer.acceptLicence()
            while case .installing = installer.state { try await Task.sleep(for: .seconds(1)) }
        }
        XCTAssertEqual(installer.state, .ready)

        let text = "I will serve as a support chatbot on your site or a helper or something like that."
        let out = directory.appendingPathComponent("variants", isDirectory: true)
        try FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)

        for steps in [16, 32] {
            let engine = F5SpeechEngine(bundleDirectory: installer.modelDirectory, steps: steps)
            let raw = try await engine.synthesize(sentence: text, voice: voice)
            try Self.writeWAV(raw, to: out.appendingPathComponent("steps\(steps)-raw.wav"))
            print("steps \(steps): \(String(format: "%.2f", Double(raw.count) / 24_000))s, "
                  + "peak \(String(format: "%.2f", raw.map(abs).max() ?? 0))")

            // What the app writes today, with and without the stretch.
            let selection = 6.46
            let spoken = try await SpeechReplacementRenderer.speak(
                text: text, selection: selection, voice: voice, using: engine
            )
            try SpeechReplacementRenderer.write(spoken, to: out.appendingPathComponent("steps\(steps)-app-pipeline.m4a"))
        }
    }

    private static func writeWAV(_ samples: [Float], to url: URL) throws {
        let file = try AVAudioFile(forWriting: url, settings: [
            AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 24_000, AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false
        ], commonFormat: .pcmFormatFloat32, interleaved: false)
        let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(samples.count))!
        buffer.frameLength = AVAudioFrameCount(samples.count)
        samples.withUnsafeBufferPointer { buffer.floatChannelData![0].update(from: $0.baseAddress!, count: samples.count) }
        try file.write(from: buffer)
    }
}
