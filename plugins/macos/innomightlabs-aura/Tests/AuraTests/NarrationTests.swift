import AVFoundation
import CryptoKit
import XCTest
@testable import Aura

/// Tone of a known length, standing in for a voice, so durations are exact and nothing is spoken.
private final class FakeVoice: SpeechSynthesizing, @unchecked Sendable {
    private let lock = NSLock()
    private var _spoken: [String] = []
    var spoken: [String] { lock.withLock { _spoken } }
    let secondsPerSentence: Double

    init(secondsPerSentence: Double = 0.5) { self.secondsPerSentence = secondsPerSentence }

    func synthesize(sentence: String, voice: VoiceSample) async throws -> [Float] {
        lock.withLock { _spoken.append(sentence) }
        let count = Int(secondsPerSentence * SpeechAudio.sampleRate)
        return (0..<count).map { Float(sin(Double($0) * 0.05)) * 0.2 }
    }
}

final class NarrationTests: XCTestCase {
    private let sample = VoiceSample(audioURL: URL(fileURLWithPath: "/unused.wav"), text: "unused")

    private func spec(intro: String? = nil, outro: String? = nil, steps: [DemoStep]) -> DemoSpec {
        DemoSpec(title: "Demo", startURL: URL(string: "https://app.example.com/")!,
                 allowedOrigins: ["https://app.example.com"], window: WindowSize(width: 1440, height: 900),
                 intro: intro, outro: outro, steps: steps)
    }

    private func step(_ id: String, narration: String?, action: DemoAction = .wait(seconds: 0)) -> DemoStep {
        DemoStep(id: id, action: action, intent: id, narration: narration)
    }

    // MARK: - Plan

    func testThePlanIsIntroThenStepsThenOutroInOrder() {
        let plan = NarrationPlan.items(for: spec(
            intro: "Welcome.", outro: "Done.",
            steps: [step("a", narration: "First."), step("b", narration: nil), step("c", narration: "Third.")]
        ))
        XCTAssertEqual(plan.map(\.slot), [.intro, .step("a"), .step("c"), .outro])
        XCTAssertEqual(plan.map(\.text), ["Welcome.", "First.", "Third.", "Done."])
    }

    func testBlankLinesAndHandoversAreNotSpoken() {
        let plan = NarrationPlan.items(for: spec(
            intro: "   ", outro: "",
            steps: [
                step("login", narration: "Sign in now.", action: .handover(reason: .login, doneWhen: nil)),
                step("a", narration: "\n  Open it.  \n"),
                step("b", narration: "  ")
            ]
        ))
        XCTAssertEqual(plan, [NarrationItem(slot: .step("a"), text: "Open it.")])
    }

    func testAStepKeepsWaitingOnlyForWhatIsLeftOfItsLine() {
        XCTAssertEqual(NarrationTiming.remainingHold(clip: 4, elapsed: 1.5), 2.5)
        XCTAssertEqual(NarrationTiming.remainingHold(clip: 4, elapsed: 9), 0, "a slow page already covered the line")
        XCTAssertEqual(NarrationTiming.remainingHold(clip: 4, elapsed: -1), 4, "never more than the whole line")
    }

    // MARK: - Rendering

    private func directory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("aura-narration-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    func testClipsAreSpokenOnceAndMeasuredFromTheFile() async throws {
        let cache = try directory()
        defer { try? FileManager.default.removeItem(at: cache) }
        let voice = FakeVoice(secondsPerSentence: 0.5)
        let items = [NarrationItem(slot: .intro, text: "One sentence."), NarrationItem(slot: .step("a"), text: "First. Second.")]

        let track = try await NarrationRenderer.render(items, voice: sample, voiceID: "fake", using: voice, cacheDirectory: cache)
        XCTAssertEqual(track.clips[.intro]?.duration ?? 0, 0.5, accuracy: 0.1)
        XCTAssertEqual(track.clips[.step("a")]?.duration ?? 0, 1.25, accuracy: 0.1, "two sentences and the gap between them")
        XCTAssertEqual(voice.spoken.count, 3)

        _ = try await NarrationRenderer.render(items, voice: sample, voiceID: "fake", using: voice, cacheDirectory: cache)
        XCTAssertEqual(voice.spoken.count, 3, "an unchanged demo is not spoken again")

        _ = try await NarrationRenderer.render(items, voice: sample, voiceID: "another voice", using: voice, cacheDirectory: cache)
        XCTAssertEqual(voice.spoken.count, 6, "a different voice speaks everything again")

        var edited = items
        edited[1] = NarrationItem(slot: .step("a"), text: "Changed.")
        _ = try await NarrationRenderer.render(edited, voice: sample, voiceID: "fake", using: voice, cacheDirectory: cache)
        XCTAssertEqual(voice.spoken.count, 7, "only the line that changed is spoken again")
    }

    func testProgressReportsEachFinishedItem() async throws {
        let cache = try directory()
        defer { try? FileManager.default.removeItem(at: cache) }
        let reported = Locked<[Int]>([])
        _ = try await NarrationRenderer.render(
            [NarrationItem(slot: .intro, text: "A."), NarrationItem(slot: .outro, text: "B.")],
            voice: sample, voiceID: "fake", using: FakeVoice(), cacheDirectory: cache
        ) { count in reported.withLock { $0.append(count) } }
        XCTAssertEqual(reported.value, [1, 2])
    }

    func testCancellingStopsBeforeSpeakingTheRest() async throws {
        let cache = try directory()
        defer { try? FileManager.default.removeItem(at: cache) }
        let voice = FakeVoice()
        let sample = self.sample
        let task = Task {
            try await NarrationRenderer.render(
                (0..<20).map { NarrationItem(slot: .step("s\($0)"), text: "Line \($0).") },
                voice: sample, voiceID: "fake", using: voice, cacheDirectory: cache
            )
        }
        task.cancel()
        do { _ = try await task.value; XCTFail("Expected cancellation") } catch is CancellationError {}
        XCTAssertLessThan(voice.spoken.count, 20)
    }

    func testCacheKeysAreStableAndDependOnTheTextAndTheVoice() {
        XCTAssertEqual(NarrationRenderer.cacheKey(text: "Hi", voiceID: "a"), NarrationRenderer.cacheKey(text: "Hi", voiceID: "a"))
        XCTAssertNotEqual(NarrationRenderer.cacheKey(text: "Hi", voiceID: "a"), NarrationRenderer.cacheKey(text: "Hi", voiceID: "b"))
        XCTAssertNotEqual(NarrationRenderer.cacheKey(text: "Hi", voiceID: "a"), NarrationRenderer.cacheKey(text: "Hi!", voiceID: "a"))
        XCTAssertEqual(NarrationRenderer.cacheKey(text: "Hi", voiceID: "a").count, 32)
    }

    func testCacheVersionInvalidatesLegacyClipsWithoutDeletingThem() async throws {
        let cache = try directory()
        defer { try? FileManager.default.removeItem(at: cache) }
        let text = "Welcome."
        let voiceID = "system:resolved-voice"
        let legacyKey = SHA256.hash(data: Data((voiceID + "\n" + text).utf8))
            .prefix(16).map { String(format: "%02x", $0) }.joined()
        let legacy = cache.appendingPathComponent(legacyKey).appendingPathExtension("m4a")
        let original = Data("old cached clip".utf8)
        try original.write(to: legacy)
        let expected = SHA256.hash(data: Data((NarrationRenderer.cacheVersion + "\n" + voiceID + "\n" + text).utf8))
            .prefix(16).map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(NarrationRenderer.cacheKey(text: text, voiceID: voiceID), expected)
        XCTAssertNotEqual(expected, legacyKey)

        let voice = FakeVoice()
        let track = try await NarrationRenderer.render(
            [NarrationItem(slot: .intro, text: text)], voice: sample, voiceID: voiceID,
            using: voice, cacheDirectory: cache)
        XCTAssertEqual(voice.spoken, [text])
        XCTAssertEqual(track.clips[.intro]?.url.lastPathComponent, expected + ".m4a")
        XCTAssertEqual(try Data(contentsOf: legacy), original)
    }

    // MARK: - Voice selection without installed assets

    private func describedVoice(
        _ identifier: String, name: String = "Voice", language: String = "en-US",
        quality: Int = 1, novelty: Bool = false
    ) -> SystemSpeechSynthesizer.VoiceDescription {
        .init(identifier: identifier, name: name, language: language, quality: quality, isNovelty: novelty)
    }

    func testAutomaticSelectionExcludesNoveltyButHonorsExplicitSelection() {
        let voices = [describedVoice("albert", name: "Albert", quality: 3, novelty: true),
                      describedVoice("samantha", name: "Samantha")]
        XCTAssertEqual(SystemSpeechSynthesizer.selectedIdentifier(
            requested: nil, voices: voices, locale: "en-US", defaultIdentifier: "albert"), "samantha")
        XCTAssertEqual(SystemSpeechSynthesizer.selectedIdentifier(
            requested: "albert", voices: voices, locale: "en-US", defaultIdentifier: "samantha"), "albert")
        XCTAssertNil(SystemSpeechSynthesizer.selectedIdentifier(
            requested: nil, voices: [voices[0]], locale: "en-US", defaultIdentifier: "albert"))
    }

    func testVoiceRankingIsQualityThenLocaleThenDefaultThenDeterministicNameAndIdentifier() {
        let voices = [
            describedVoice("z", name: "Zulu"),
            describedVoice("b", name: "Alpha"), describedVoice("a", name: "Alpha"),
            describedVoice("default", name: "Zulu"),
            describedVoice("gb", name: "Aardvark", language: "en-GB"),
            describedVoice("enhanced", language: "en-GB", quality: 2),
            describedVoice("premium", language: "en-GB", quality: 3),
            describedVoice("french", language: "fr-FR", quality: 3)
        ]
        let ranked = SystemSpeechSynthesizer.rankedVoices(
            voices + [voices[0]], language: "en", locale: "en_US", defaultIdentifier: "default")
        XCTAssertEqual(ranked.map(\.identifier), ["premium", "enhanced", "default", "a", "b", "z", "gb"])
        XCTAssertEqual(ranked, SystemSpeechSynthesizer.rankedVoices(
            Array(voices.reversed()), language: "en", locale: "en-US", defaultIdentifier: "default"))
    }

    func testMissingSelectionUsesActualFallbackIdentityAndInventoryChangesInvalidateCache() throws {
        let first = describedVoice("first", quality: 1)
        let better = describedVoice("better", quality: 2)
        let old = try XCTUnwrap(SystemSpeechSynthesizer.selectedIdentifier(
            requested: nil, voices: [first], locale: "en-US", defaultIdentifier: first.identifier))
        let fallback = try XCTUnwrap(SystemSpeechSynthesizer.selectedIdentifier(
            requested: "removed", voices: [first, better], locale: "en-US", defaultIdentifier: first.identifier))
        let automatic = SystemSpeechSynthesizer.selectedIdentifier(
            requested: nil, voices: [first, better], locale: "en-US", defaultIdentifier: first.identifier)
        XCTAssertEqual(fallback, "better")
        XCTAssertEqual(automatic, fallback)
        XCTAssertNotEqual(NarrationRenderer.cacheKey(text: "Hello.", voiceID: "system:\(old)"),
                          NarrationRenderer.cacheKey(text: "Hello.", voiceID: "system:\(fallback)"))
        XCTAssertNil(SystemSpeechSynthesizer.selectedIdentifier(
            requested: "removed", voices: [], locale: "en-US", defaultIdentifier: nil))
    }

    func testAutomaticFallbackCanUseConventionalSystemDefaultOutsideTheLocale() {
        let voices = [describedVoice("default", language: "en-GB"),
                      describedVoice("novelty", language: "fr-FR", novelty: true)]
        XCTAssertEqual(SystemSpeechSynthesizer.selectedIdentifier(
            requested: nil, voices: voices, locale: "fr-FR", defaultIdentifier: "default"), "default")
        XCTAssertNil(SystemSpeechSynthesizer.selectedIdentifier(
            requested: nil, voices: voices, locale: "fr-FR", defaultIdentifier: "novelty"))
    }

    // MARK: - PCM conversion

    private func tone(rate: Double, seconds: Double = 1, phase: Double = 0) throws -> AVAudioPCMBuffer {
        let format = try XCTUnwrap(AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: rate,
                                                channels: 1, interleaved: false))
        let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(rate * seconds)))
        buffer.frameLength = buffer.frameCapacity
        for index in 0..<Int(buffer.frameLength) {
            buffer.floatChannelData![0][index] = Float(sin(2 * .pi * 440 * (Double(index) / rate + phase))) * 0.5
        }
        return buffer
    }

    func testMismatchedPCMFormatsThrowRatherThanDroppingAudio() throws {
        let buffers = try [tone(rate: 24_000), tone(rate: 48_000)]
        XCTAssertThrowsError(try SystemSpeechSynthesizer.samples(from: buffers)) { error in
            guard case SystemSpeechSynthesizer.SynthesisError.mismatchedAudioFormats = error else {
                return XCTFail("Expected a format mismatch, got \(error)")
            }
        }
        XCTAssertTrue(try SystemSpeechSynthesizer.samples(from: []).isEmpty)
    }

    func testKnownTonesKeepDurationFrequencyAndAmplitudeAcrossSampleRates() throws {
        for rate in [22_050.0, 24_000, 32_000, 44_100, 48_000] {
            let samples = try SystemSpeechSynthesizer.samples(from: [tone(rate: rate)])
            XCTAssertEqual(Double(samples.count) / SpeechAudio.sampleRate, 1, accuracy: 0.002)
            let crossings = zip(samples, samples.dropFirst()).filter { $0.0 <= 0 && $0.1 > 0 }.count
            XCTAssertEqual(Double(crossings), 440, accuracy: 2, "input rate \(rate)")
            XCTAssertEqual(samples.map { abs($0) }.max() ?? 0, 0.5, accuracy: 0.01)
            XCTAssertTrue(samples.allSatisfy(\.isFinite))
        }
    }

    func testJoiningBuffersDoesNotRestartTheConverter() throws {
        let rate = 44_100.0
        let whole = try SystemSpeechSynthesizer.samples(from: [tone(rate: rate)])
        let split = try SystemSpeechSynthesizer.samples(from: [
            tone(rate: rate, seconds: 0.5), tone(rate: rate, seconds: 0.5, phase: 0.5)
        ])
        XCTAssertEqual(split.count, whole.count)
        XCTAssertLessThan(zip(split, whole).map { abs($0.0 - $0.1) }.max() ?? 0, 0.00001)
    }

    // MARK: - The system voice

    func testTheSystemVoiceSpeaksAndAnythingItMakesIsUsable() async throws {
        guard !SystemSpeechSynthesizer.availableVoices().isEmpty else { throw XCTSkip("This Mac has no voice installed.") }
        let resolved = try NarrationVoice.resolve()
        XCTAssertEqual(resolved.cacheID, "system:\(resolved.synthesizer.voiceIdentifier)")
        let samples = try await resolved.synthesizer.synthesize(sentence: "Open the agent builder.", voice: sample)
        let seconds = Double(samples.count) / SpeechAudio.sampleRate
        XCTAssertGreaterThan(seconds, 0.4, "a sentence is not a fraction of a second")
        XCTAssertLessThan(seconds, 10)
        XCTAssertGreaterThan(samples.map { abs($0) }.max() ?? 0, 0.01, "and is not silence")
        XCTAssertTrue(samples.allSatisfy { $0.isFinite && abs($0) <= 1.5 })

        // And it goes all the way through the renderer into a readable clip.
        let cache = try directory()
        defer { try? FileManager.default.removeItem(at: cache) }
        let track = try await NarrationRenderer.render(
            [NarrationItem(slot: .intro, text: "Welcome to the demo.")],
            voice: sample, voiceID: resolved.cacheID, using: resolved.synthesizer, cacheDirectory: cache)
        XCTAssertGreaterThan(track.clips[.intro]?.duration ?? 0, 0.4)
    }
}

private final class Locked<Value>: @unchecked Sendable {
    private let lock = NSLock()
    private var stored: Value
    init(_ value: Value) { stored = value }
    var value: Value { lock.withLock { stored } }
    func withLock(_ body: (inout Value) -> Void) { lock.withLock { body(&stored) } }
}
