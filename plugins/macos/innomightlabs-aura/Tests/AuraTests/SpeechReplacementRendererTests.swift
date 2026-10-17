import XCTest
import AVFoundation
@testable import Aura

final class SpeechReplacementRendererTests: XCTestCase {
    private var directory: URL!
    private let voice = VoiceSample(audioURL: URL(fileURLWithPath: "/tmp/ref.wav"), text: "reference")

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-render-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    /// Speaks a sentence as a tone one second long per `charactersPerSecond` characters.
    private final class FakeSynthesizer: SpeechSynthesizing, @unchecked Sendable {
        private let lock = NSLock()
        private var sentences: [String] = []
        var failOn: String?
        var spoken: [String] { lock.withLock { sentences } }

        func synthesize(sentence: String, voice: VoiceSample) async throws -> [Float] {
            lock.withLock { sentences.append(sentence) }
            if sentence == failOn { throw NSError(domain: "fake", code: 1) }
            let seconds = Double(sentence.count) / 10   // 10 characters a second
            let rate = SpeechAudio.sampleRate
            return (0..<Int(seconds * rate)).map { 0.3 * Float(sin(2 * Double.pi * 220 * Double($0) / rate)) }
        }
    }

    private func length(of url: URL) throws -> Double {
        let file = try AVAudioFile(forReading: url)
        return Double(file.length) / file.processingFormat.sampleRate
    }

    // MARK: - Speaking

    func testEachSentenceIsSpokenSeparatelyInOrder() async throws {
        let fake = FakeSynthesizer()
        let spoken = try await SpeechReplacementRenderer.speak(
            text: "First one here. Second one there! Third?", selection: 5, voice: voice, using: fake
        )

        XCTAssertEqual(fake.spoken, ["First one here.", "Second one there!", "Third?"])
        XCTAssertEqual(spoken.sentenceCount, 3)
    }

    func testSentencesAreJoinedWithANaturalGap() async throws {
        // 15 + 16 characters at 10 a second is 3.1s of speech, plus one 0.25s gap, and a
        // selection long enough that nothing else is done to it.
        let spoken = try await SpeechReplacementRenderer.speak(
            text: "First one here. Second one there!", selection: 3.35, voice: voice, using: FakeSynthesizer()
        )
        XCTAssertEqual(spoken.fit.clipDuration, 3.35, accuracy: 0.001)
    }

    func testEmptyTextHasNothingToSay() async {
        do {
            _ = try await SpeechReplacementRenderer.speak(text: " ... ", selection: 3, voice: voice, using: FakeSynthesizer())
            XCTFail("expected an error")
        } catch {
            XCTAssertEqual(error as? SpeechRenderError, .nothingToSay)
        }
    }

    func testSpeechThatRunsLongKeepsItsLengthAndAsksForAHold() async throws {
        // 70 characters is 7s against a 4s selection.
        let text = String(repeating: "a", count: 69) + "."
        let spoken = try await SpeechReplacementRenderer.speak(text: text, selection: 4, voice: voice, using: FakeSynthesizer())

        XCTAssertEqual(spoken.fit.action, .hold)
        XCTAssertEqual(spoken.fit.clipDuration, 7, accuracy: 0.01)
        XCTAssertEqual(spoken.fit.hold, 3, accuracy: 0.01)
    }

    func testProgressCountsSentences() async throws {
        let seen = Locked<Double>()
        _ = try await SpeechReplacementRenderer.speak(
            text: "One. Two. Three. Four.", selection: 2, voice: voice, using: FakeSynthesizer()
        ) { seen.append($0) }

        XCTAssertEqual(seen.values, [0.25, 0.5, 0.75, 1])
    }

    func testAFailingSentenceFailsTheWholeRenderAndWritesNothing() async throws {
        let fake = FakeSynthesizer()
        fake.failOn = "Two."
        let destination = directory.appendingPathComponent("clip.m4a")

        do {
            let spoken = try await SpeechReplacementRenderer.speak(text: "One. Two. Three.", selection: 2, voice: voice, using: fake)
            try SpeechReplacementRenderer.write(spoken, to: destination)
            XCTFail("expected an error")
        } catch {}

        XCTAssertFalse(FileManager.default.fileExists(atPath: destination.path))
        XCTAssertEqual(fake.spoken, ["One.", "Two."], "no sentence is spoken after one has failed")
    }

    func testCancellingStopsBetweenSentences() async throws {
        let fake = FakeSynthesizer()
        let voice = self.voice
        let task = Task {
            try await SpeechReplacementRenderer.speak(
                text: "One. Two. Three. Four. Five.", selection: 2, voice: voice, using: fake
            )
        }
        task.cancel()

        do {
            _ = try await task.value
            XCTFail("a cancelled render should throw")
        } catch is CancellationError {}
    }

    // MARK: - Writing

    func testAClipThatFitsIsExactlyTheSelectionLong() async throws {
        // 4.4s of speech into 4s: stretched, and exactly 4s afterwards.
        let text = String(repeating: "a", count: 43) + "."
        let spoken = try await SpeechReplacementRenderer.speak(text: text, selection: 4, voice: voice, using: FakeSynthesizer())
        let url = directory.appendingPathComponent("stretch.m4a")

        let duration = try SpeechReplacementRenderer.write(spoken, to: url)

        XCTAssertEqual(duration, 4, accuracy: 0.001)
        XCTAssertEqual(try length(of: url), 4, accuracy: 0.05)
    }

    func testShortSpeechIsPaddedToTheSelection() async throws {
        let spoken = try await SpeechReplacementRenderer.speak(text: "Hi there.", selection: 4, voice: voice, using: FakeSynthesizer())
        let url = directory.appendingPathComponent("pad.m4a")

        XCTAssertEqual(try SpeechReplacementRenderer.write(spoken, to: url), 4, accuracy: 0.001)
        XCTAssertEqual(try length(of: url), 4, accuracy: 0.05)
    }

    func testLongSpeechKeepsItsOwnLength() async throws {
        let text = String(repeating: "a", count: 69) + "."
        let spoken = try await SpeechReplacementRenderer.speak(text: text, selection: 4, voice: voice, using: FakeSynthesizer())
        let url = directory.appendingPathComponent("hold.m4a")

        XCTAssertEqual(try SpeechReplacementRenderer.write(spoken, to: url), 7, accuracy: 0.01)
        XCTAssertEqual(try length(of: url), 7, accuracy: 0.05)
    }

    func testTheClipFadesInAndOutSoItCannotClick() async throws {
        let spoken = try await SpeechReplacementRenderer.speak(text: "A steady tone for a while.", selection: 2.6, voice: voice, using: FakeSynthesizer())
        let url = directory.appendingPathComponent("fade.m4a")
        try SpeechReplacementRenderer.write(spoken, to: url)

        let file = try AVAudioFile(forReading: url)
        let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: 4_800)!
        try file.read(into: buffer, frameCount: 4_800)
        let head = UnsafeBufferPointer(start: buffer.floatChannelData![0], count: 48)
        XCTAssertLessThan(head.map(abs).max() ?? 1, 0.1, "the first couple of milliseconds should be near silent")
    }

    func testWritingReplacesAnExistingClipAndLeavesNoTemporaryFile() async throws {
        let url = directory.appendingPathComponent("replacements/clip.m4a")
        for text in ["One short.", "Another short one."] {
            let spoken = try await SpeechReplacementRenderer.speak(text: text, selection: 2, voice: voice, using: FakeSynthesizer())
            try SpeechReplacementRenderer.write(spoken, to: url)
        }

        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: url.deletingLastPathComponent().path), ["clip.m4a"])
    }
}

/// Collects values from a `@Sendable` callback.
private final class Locked<Value>: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [Value] = []
    func append(_ value: Value) { lock.withLock { storage.append(value) } }
    var values: [Value] { lock.withLock { storage } }
}
