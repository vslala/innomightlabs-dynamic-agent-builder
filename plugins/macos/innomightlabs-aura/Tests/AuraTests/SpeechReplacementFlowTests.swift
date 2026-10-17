import XCTest
import AVFoundation
import CryptoKit
@testable import Aura

/// The whole path a user takes, through the real view model with a fake voice: ask for new
/// words, have them spoken, see them in the document, the transcript and the player.
@MainActor
final class SpeechReplacementFlowTests: XCTestCase {
    private var root: URL!
    private var folder: SessionFolder!
    private var defaultsSuite: String!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-speech-flow-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        folder = SessionFolder.load(rootURL: root)
        defaultsSuite = "aura-speech-flow-\(UUID().uuidString)"
        SpeechPreferences.suppressesCameraWarning = false
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: root)
        UserDefaults(suiteName: defaultsSuite)?.removePersistentDomain(forName: defaultsSuite)
        SpeechPreferences.suppressesCameraWarning = false
    }

    // MARK: - Fixtures

    /// 10 characters of text make a second of speech.
    private final class FakeVoice: SpeechSynthesizing, @unchecked Sendable {
        func synthesize(sentence: String, voice: VoiceSample) async throws -> [Float] {
            let rate = SpeechAudio.sampleRate
            return (0..<Int(Double(sentence.count) / 10 * rate)).map {
                0.3 * Float(sin(2 * Double.pi * 220 * Double($0) / rate))
            }
        }
    }

    private final class InstantDownloader: FileDownloading, @unchecked Sendable {
        let contents: [String: Data]
        init(_ contents: [String: Data]) { self.contents = contents }
        func download(_ url: URL, to destination: URL, progress: @escaping @Sendable (Int64) -> Void) async throws {
            try (contents[url.lastPathComponent] ?? Data()).write(to: destination)
        }
    }

    /// A hub whose model is "installed" and whose voice is the fake.
    private func readyHub() async -> SpeechEngineHub {
        let data = Data("model".utf8)
        let bundle = SpeechModelBundle(
            repository: "x/y", revision: "r", files: [
                .init(name: "m.bin", bytes: Int64(data.count), sha256: SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined())
            ],
            licenceName: "Test", licenceURL: URL(string: "https://example.com")!, modelCardURL: URL(string: "https://example.com")!
        )
        let installer = SpeechEngineInstaller(
            bundle: bundle, engineDirectory: root.appendingPathComponent("engine"),
            defaults: UserDefaults(suiteName: defaultsSuite)!,
            downloader: InstantDownloader(["m.bin": data]), freeSpace: { _ in 10_000_000_000 }
        )
        installer.beginEnabling()
        installer.acceptLicence()
        while installer.state != .ready { try? await Task.sleep(for: .milliseconds(10)) }
        return SpeechEngineHub(installer: installer, makeEngine: { _ in FakeVoice() })
    }

    /// 20 s of media, and a transcript of 60 words at three a second in two lines:
    /// words 0–19 (0–6.6 s) and words 20–59 (6.7–19.9 s).
    private func writeSession(withCamera: Bool = false) async throws {
        try await TestMedia.writeVideo(to: folder.screenURL, seconds: 20)
        if withCamera { try await TestMedia.writeVideo(to: folder.cameraURL, seconds: 20) }
        try TestMedia.writeSilentAudio(to: folder.microphoneURL, seconds: 20)
        try Data(#"{"ts":0,"type":"record_start","media_ts":0}"#.utf8).write(to: folder.eventsURL)

        func word(_ index: Int, last: Bool) -> Transcript.Word {
            let start = Double(index) / 3
            return Transcript.Word(id: index, start: start, end: start + 0.3, text: "word\(index)" + (last ? "." : ""))
        }
        let first = (0..<20).map { word($0, last: $0 == 19) }
        let second = (20..<60).map { word($0, last: $0 == 59) }
        Transcript(source: "microphone.m4a", engine: "test", language: "en", segments: [
            Transcript.Segment(id: 0, start: 0, end: 6.6, text: first.map(\.text).joined(separator: " "), words: first),
            Transcript.Segment(id: 1, start: 6.7, end: 19.9, text: second.map(\.text).joined(separator: " "), words: second)
        ]).write(to: folder.transcriptURL)
    }

    private func openWindow(hub: SpeechEngineHub? = nil) async throws -> ReviewViewModel {
        let hub = await readyHubIfNeeded(hub)
        let viewModel = ReviewViewModel(folder: folder, speech: hub)
        await viewModel.load()
        XCTAssertEqual(viewModel.state, .ready)
        try await eventually("the transcript to load") { viewModel.transcript != nil }
        return viewModel
    }

    private func readyHubIfNeeded(_ hub: SpeechEngineHub?) async -> SpeechEngineHub {
        if let hub { return hub }
        return await readyHub()
    }

    private func eventually(_ what: String, timeout: Double = 15, _ condition: () -> Bool) async throws {
        var waited = 0.0
        while !condition() {
            guard waited < timeout else { return XCTFail("timed out waiting for \(what)") }
            try await Task.sleep(for: .milliseconds(50))
            waited += 0.05
        }
    }

    private func finishSpeaking(_ viewModel: ReviewViewModel) async throws {
        try await eventually("speaking to finish") {
            viewModel.speechTask == nil && !viewModel.isSpeaking && viewModel.pendingSpeech == nil
        }
    }

    // MARK: - Tests

    func testReplacingALineSpeaksItAndRecordsTheEdit() async throws {
        try await writeSession()
        let viewModel = try await openWindow()
        let before = Timeline.seconds(viewModel.duration)

        viewModel.replaceSpeech(span: TimeSpan(start: 1, end: 7), text: "Hello there my friend.", originalText: "old")
        try await finishSpeaking(viewModel)

        let replacement = try XCTUnwrap(viewModel.store?.document.speechReplacements.first)
        XCTAssertEqual(replacement.text, "Hello there my friend.")
        XCTAssertEqual(replacement.originalText, "old")
        XCTAssertEqual(replacement.duration, 6, accuracy: 0.01, "2.2s of speech padded to its 6s slot")
        XCTAssertTrue(FileManager.default.fileExists(atPath: folder.speechClipURL(for: replacement.id).path))
        XCTAssertEqual(viewModel.lastNotice, "Replaced in your voice.")
        XCTAssertEqual(Timeline.seconds(viewModel.duration), before, accuracy: 0.05)
        viewModel.close()
    }

    func testSpeechThatRunsLongExtendsThePlayersItem() async throws {
        try await writeSession()
        let viewModel = try await openWindow()
        let before = Timeline.seconds(viewModel.duration)

        // 9 s of speech into a 3 s slot: the picture holds for 6 s.
        viewModel.replaceSpeech(span: TimeSpan(start: 1, end: 4), text: String(repeating: "a", count: 89) + ".", originalText: "old")
        try await finishSpeaking(viewModel)
        try await eventually("the rebuild") { abs(Timeline.seconds(viewModel.duration) - (before + 6)) < 0.2 }

        XCTAssertEqual(CMTimeGetSeconds(viewModel.player.currentItem?.asset.duration ?? .zero), before + 6, accuracy: 0.2)
        XCTAssertTrue(viewModel.lastNotice?.contains("holds for") == true, viewModel.lastNotice ?? "no notice")
        viewModel.close()
    }

    func testAVeryLongHoldWaitsForTheUserAndDecliningChangesNothing() async throws {
        try await writeSession()
        let viewModel = try await openWindow()
        let long = String(repeating: "x", count: 119) + ". " + String(repeating: "y", count: 119) + "."

        viewModel.replaceSpeech(span: TimeSpan(start: 1, end: 4), text: long, originalText: "old")
        try await eventually("the hold question") { viewModel.pendingSpeech != nil }

        guard case .longHold(_, let seconds) = viewModel.pendingSpeech else { return XCTFail("wrong prompt") }
        XCTAssertGreaterThan(seconds, DurationFitter.confirmationThreshold)
        XCTAssertTrue(viewModel.store?.document.speechReplacements.isEmpty == true, "nothing applied before the answer")

        viewModel.declinePendingSpeech()
        try await finishSpeaking(viewModel)
        XCTAssertTrue(viewModel.store?.document.speechReplacements.isEmpty == true)
        viewModel.close()
    }

    func testAcceptingALongHoldApplies() async throws {
        try await writeSession()
        let viewModel = try await openWindow()
        let before = Timeline.seconds(viewModel.duration)
        // About 24 s of speech into 3 s: a hold of roughly 21 s, which is the user's to approve.
        let long = String(repeating: "x", count: 119) + ". " + String(repeating: "y", count: 119) + "."
        viewModel.replaceSpeech(span: TimeSpan(start: 1, end: 4), text: long, originalText: "old")
        try await eventually("the hold question") { viewModel.pendingSpeech != nil }

        viewModel.acceptLongHold()

        let replacement = try XCTUnwrap(viewModel.store?.document.speechReplacements.first)
        XCTAssertEqual(replacement.hold, 21.25, accuracy: 0.1)
        try await eventually("the rebuild") { abs(Timeline.seconds(viewModel.duration) - (before + replacement.hold)) < 0.3 }
        viewModel.close()
    }

    func testTheCameraWarningAsksOnceAndRemembersWhenTold() async throws {
        try await writeSession(withCamera: true)
        let viewModel = try await openWindow()

        viewModel.replaceSpeech(span: TimeSpan(start: 1, end: 7), text: "Hello there.", originalText: "old")
        guard case .cameraWarning = viewModel.pendingSpeech else { return XCTFail("expected a warning, got \(String(describing: viewModel.pendingSpeech))") }
        XCTAssertTrue(viewModel.store?.document.speechReplacements.isEmpty == true)

        viewModel.confirmCameraWarning(rememberChoice: true)
        try await finishSpeaking(viewModel)
        XCTAssertEqual(viewModel.store?.document.speechReplacements.count, 1)
        XCTAssertTrue(SpeechPreferences.suppressesCameraWarning)

        // Remembered: the next one goes straight through.
        viewModel.replaceSpeech(span: TimeSpan(start: 9, end: 12), text: "And another.", originalText: "old")
        XCTAssertNil(viewModel.pendingSpeech)
        try await finishSpeaking(viewModel)
        XCTAssertEqual(viewModel.store?.document.speechReplacements.count, 2)
        viewModel.close()
    }

    func testCancellingTheCameraWarningDoesNothing() async throws {
        try await writeSession(withCamera: true)
        let viewModel = try await openWindow()

        viewModel.replaceSpeech(span: TimeSpan(start: 1, end: 7), text: "Hello there.", originalText: "old")
        viewModel.declinePendingSpeech()
        try await finishSpeaking(viewModel)

        XCTAssertTrue(viewModel.store?.document.speechReplacements.isEmpty == true)
        XCTAssertFalse(SpeechPreferences.suppressesCameraWarning)
        viewModel.close()
    }

    func testWithoutTheModelInstalledTheUserIsSentToSetItUp() async throws {
        try await writeSession()
        let notReady = SpeechEngineHub(installer: SpeechEngineInstaller(
            engineDirectory: root.appendingPathComponent("none"), defaults: UserDefaults(suiteName: defaultsSuite)!
        ))
        let viewModel = try await openWindow(hub: notReady)

        viewModel.replaceSpeech(span: TimeSpan(start: 1, end: 7), text: "Hello.", originalText: "old")

        XCTAssertTrue(viewModel.speechSetupRequested)
        XCTAssertTrue(viewModel.store?.document.speechReplacements.isEmpty == true)
        viewModel.close()
    }

    func testEditingATranscriptLineReplacesThatLinesSpeech() async throws {
        try await writeSession()
        let viewModel = try await openWindow()
        let cue = try XCTUnwrap(viewModel.projection.cues.first)

        viewModel.commitEdit(of: cue, to: "A completely different opening line.")
        try await finishSpeaking(viewModel)

        let replacement = try XCTUnwrap(viewModel.store?.document.speechReplacements.first)
        XCTAssertEqual(replacement.span.start, 0, accuracy: 0.01)
        XCTAssertEqual(replacement.span.end, 19.0 / 3 + 0.3, accuracy: 0.01, "the cue's first word to its last")
        XCTAssertTrue(replacement.originalText.hasPrefix("word0 word1"))

        try await eventually("the transcript to show it") { viewModel.projection.cues.first?.replacementID != nil }
        let shown = try XCTUnwrap(viewModel.projection.cues.first)
        XCTAssertEqual(shown.text, "A completely different opening line.")
        XCTAssertEqual(shown.replacementID, replacement.id)
        XCTAssertEqual(viewModel.projection.cues.count, 2, "the other line is untouched")
        viewModel.close()
    }

    func testAnUnchangedLineIsLeftAlone() async throws {
        try await writeSession()
        let viewModel = try await openWindow()
        let cue = try XCTUnwrap(viewModel.projection.cues.first)

        viewModel.commitEdit(of: cue, to: "  " + cue.text + " \n")

        XCTAssertNil(viewModel.pendingSpeech)
        XCTAssertFalse(viewModel.isSpeaking)
        XCTAssertTrue(viewModel.store?.document.speechReplacements.isEmpty == true)
        XCTAssertNotNil(viewModel.lastNotice)
        viewModel.close()
    }

    func testEditingAReplacedLineAgainSwapsItInsteadOfStackingAnother() async throws {
        try await writeSession()
        let viewModel = try await openWindow()
        viewModel.commitEdit(of: try XCTUnwrap(viewModel.projection.cues.first), to: "First version of the line.")
        try await finishSpeaking(viewModel)
        let first = try XCTUnwrap(viewModel.store?.document.speechReplacements.first)
        try await eventually("the transcript to show it") { viewModel.projection.cues.first?.replacementID != nil }

        viewModel.commitEdit(of: try XCTUnwrap(viewModel.projection.cues.first), to: "Second version of the line.")
        try await finishSpeaking(viewModel)

        let replacements = try XCTUnwrap(viewModel.store?.document.speechReplacements)
        XCTAssertEqual(replacements.count, 1)
        XCTAssertEqual(replacements[0].id, first.id)
        XCTAssertEqual(replacements[0].text, "Second version of the line.")
        XCTAssertEqual(replacements[0].originalText, first.originalText, "still remembers what was really said")
        viewModel.close()
    }

    func testRestoringTheOriginalVoiceUndoesItAndUndoBringsTheNewOneBack() async throws {
        try await writeSession()
        let viewModel = try await openWindow()
        viewModel.commitEdit(of: try XCTUnwrap(viewModel.projection.cues.first), to: "Something new to say.")
        try await finishSpeaking(viewModel)

        try await eventually("the transcript to show it") { viewModel.projection.cues.first?.replacementID != nil }

        viewModel.restoreOriginalVoice(of: try XCTUnwrap(viewModel.projection.cues.first))
        XCTAssertTrue(viewModel.store?.document.speechReplacements.isEmpty == true)
        try await eventually("the original back") { viewModel.projection.cues.first?.replacementID == nil }

        viewModel.store?.undo()
        XCTAssertEqual(viewModel.store?.document.speechReplacements.count, 1, "the clip is kept, so undo needs no re-speaking")
        viewModel.close()
    }

    func testAcceptingAnAgentSuggestionSpeaksItAndRemovesIt() async throws {
        try await writeSession()
        let viewModel = try await openWindow()
        let draft = SpeechReplacement(span: TimeSpan(start: 7, end: 12), text: "The agent's better sentence.")

        viewModel.accept(EditSuggestion(operation: .replaceSpeech(draft), rationale: "garbled"))
        try await finishSpeaking(viewModel)

        let replacement = try XCTUnwrap(viewModel.store?.document.speechReplacements.first)
        XCTAssertEqual(replacement.id, draft.id)
        XCTAssertEqual(replacement.text, "The agent's better sentence.")
        XCTAssertFalse(replacement.originalText.isEmpty, "what was said there is filled in from the transcript")
        viewModel.close()
    }

    func testAMissingClipIsSpokenAgainFromTheStoredText() async throws {
        try await writeSession()
        let viewModel = try await openWindow()
        viewModel.commitEdit(of: try XCTUnwrap(viewModel.projection.cues.first), to: "Something new to say.")
        try await finishSpeaking(viewModel)
        let replacement = try XCTUnwrap(viewModel.store?.document.speechReplacements.first)
        let clip = folder.speechClipURL(for: replacement.id)

        try FileManager.default.removeItem(at: clip)
        viewModel.scheduleRebuildForSpeech(document: try XCTUnwrap(viewModel.store?.document))

        try await eventually("the clip to be made again") { FileManager.default.fileExists(atPath: clip.path) }
        viewModel.close()
    }

    func testASessionWithNoClearVoiceSaysSoInsteadOfGuessing() async throws {
        try await writeSession()
        // Fillers every few words leave no 6 second stretch of fluent speech.
        let words = (0..<60).map { index -> Transcript.Word in
            let start = Double(index) / 3
            return Transcript.Word(id: index, start: start, end: start + 0.3, text: index % 4 == 3 ? "um" : "word\(index)")
        }
        Transcript(source: "m", engine: "t", language: "en", segments: [
            Transcript.Segment(id: 0, start: 0, end: 20, text: "x", words: words)
        ]).write(to: folder.transcriptURL)
        let viewModel = try await openWindow()

        viewModel.replaceSpeech(span: TimeSpan(start: 1, end: 7), text: "Hello there.", originalText: "old")
        try await finishSpeaking(viewModel)

        XCTAssertTrue(viewModel.lastError?.contains("clear") == true, viewModel.lastError ?? "no error")
        XCTAssertTrue(viewModel.store?.document.speechReplacements.isEmpty == true)
        viewModel.close()
    }
}
