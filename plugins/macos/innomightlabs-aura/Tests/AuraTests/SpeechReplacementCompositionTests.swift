import XCTest
import AVFoundation
@testable import Aura

/// Builds real compositions with a replacement in them. The pure tests prove the document and
/// the timeline maths; these prove AVFoundation actually accepts what the builder gives it —
/// in particular the frozen picture, whose construction is the part most likely to be wrong.
@MainActor
final class SpeechReplacementCompositionTests: XCTestCase {
    private var root: URL!
    private var folder: SessionFolder!
    private var speechClip: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-speech-comp-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        folder = SessionFolder.load(rootURL: root)
        speechClip = root.appendingPathComponent("speech.m4a")
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: root)
    }

    // MARK: - Fixtures

    /// 6 s of video, 6 s of microphone, and a 5 s clip of "new speech".
    private func writeMedia() async throws {
        try await TestMedia.writeVideo(to: folder.screenURL, seconds: 6)
        try TestMedia.writeSilentAudio(to: folder.microphoneURL, seconds: 6)
        try TestMedia.writeSilentAudio(to: speechClip, seconds: 5)
        try Data(#"{"ts":0,"type":"record_start","media_ts":0}"#.utf8).write(to: folder.eventsURL)
    }

    /// The document for a 2s–4s selection replaced by a 5s clip: 3s of picture hold.
    private func document(clipSeconds: TimeInterval) throws -> SessionEdit {
        try SessionEdit.initial(duration: 6).applying(.replaceSpeech(SpeechReplacement(
            span: TimeSpan(start: 2, end: 4),
            text: "new words",
            originalText: "old words",
            duration: clipSeconds
        )))
    }

    private func build(_ document: SessionEdit, clips: [UUID: URL]) async throws -> BuiltComposition {
        let probes = await SourceTrackProbe.probeAll(in: folder)
        let resolved = TimelineResolver.resolve(document: document, probes: probes, speechClips: clips)
        return try await LayerInstructionCompositionBuilder().build(resolved)
    }

    /// Volume every audio-mix input has at `seconds`, sorted.
    private func volumes(in built: BuiltComposition, at seconds: Double) -> [Float] {
        (built.audioMix?.inputParameters ?? []).map { parameters in
            var start: Float = -1, end: Float = -1
            var range = CMTimeRange.zero
            parameters.getVolumeRamp(for: CMTime(seconds: seconds, preferredTimescale: 600),
                                     startVolume: &start, endVolume: &end, timeRange: &range)
            return start
        }.sorted()
    }

    private func coverage(_ built: BuiltComposition, _ type: AVMediaType) async throws -> [(gaps: Int, seconds: Double)] {
        var result: [(Int, Double)] = []
        for track in try await built.asset.loadTracks(withMediaType: type) {
            let segments = try await track.load(.segments)
            result.append((
                segments.filter(\.isEmpty).count,
                segments.filter { !$0.isEmpty }.reduce(0) { $0 + CMTimeGetSeconds($1.timeMapping.target.duration) }
            ))
        }
        return result
    }

    // MARK: - Tests

    func testTheOriginalVoiceIsSilencedUnderTheNewSpeechAndComesBackAfter() async throws {
        try await writeMedia()
        let edit = try document(clipSeconds: 5)
        let built = try await build(edit, clips: [edit.speechReplacements[0].id: speechClip])

        // Before, during and after the selection: two inputs (voice, new speech).
        XCTAssertEqual(volumes(in: built, at: 1), [1, 1])
        XCTAssertEqual(volumes(in: built, at: 3), [0, 1], "the voice must be silent while the new speech plays")
        XCTAssertEqual(volumes(in: built, at: 8.5), [1, 1], "the voice returns after the hold")
    }

    func testSpeechThatRunsLongKeepsThePictureUpWithNoGap() async throws {
        try await writeMedia()
        let edit = try document(clipSeconds: 5)
        let built = try await build(edit, clips: [edit.speechReplacements[0].id: speechClip])

        XCTAssertEqual(Timeline.seconds(built.duration), 9, accuracy: 0.1)

        let video = try await coverage(built, .video)
        XCTAssertEqual(video.count, 1)
        XCTAssertEqual(video[0].gaps, 0, "the hold must be filled, not left black")
        XCTAssertEqual(video[0].seconds, 9, accuracy: 0.15)
    }

    func testAFrameIsActuallyProducedInTheMiddleOfTheHold() async throws {
        try await writeMedia()
        let edit = try document(clipSeconds: 5)
        let built = try await build(edit, clips: [edit.speechReplacements[0].id: speechClip])

        let generator = AVAssetImageGenerator(asset: built.asset)
        generator.videoComposition = built.videoComposition
        generator.requestedTimeToleranceBefore = .zero
        generator.requestedTimeToleranceAfter = .zero

        // The hold covers composition 4s–7s.
        for seconds in [4.5, 5.5, 6.9] {
            // The synchronous call: the async one cannot take a non-Sendable generator from here.
            let image = try generator.copyCGImage(at: CMTime(seconds: seconds, preferredTimescale: 600), actualTime: nil)
            XCTAssertEqual(image.width, 160, "no frame at \(seconds)s")
        }
    }

    func testTheNewSpeechPlaysThroughTheSelectionAndTheHold() async throws {
        try await writeMedia()
        let edit = try document(clipSeconds: 5)
        let built = try await build(edit, clips: [edit.speechReplacements[0].id: speechClip])

        // The voice track is quiet for the hold; the speech track carries 2s + 3s of it.
        let audio = try await coverage(built, .audio)
        XCTAssertEqual(audio.count, 2)
        XCTAssertTrue(audio.contains { abs($0.seconds - 5) < 0.15 }, "expected the clip's full 5s on its own track: \(audio)")
    }

    func testAMissingClipPlaysTheOriginalVoiceButKeepsTheTimelineTheSameLength() async throws {
        try await writeMedia()
        let edit = try document(clipSeconds: 5)
        let built = try await build(edit, clips: [:])

        XCTAssertEqual(volumes(in: built, at: 3), [1], "without a clip the original voice must keep playing")
        XCTAssertEqual(Timeline.seconds(built.duration), 9, accuracy: 0.1,
                       "the timeline is defined by the document, not by whether a file exists")
    }

    func testSpeechThatFitsLeavesTheTimelineAlone() async throws {
        try await writeMedia()
        let edit = try document(clipSeconds: 2)
        let built = try await build(edit, clips: [edit.speechReplacements[0].id: speechClip])

        XCTAssertEqual(Timeline.seconds(built.duration), 6, accuracy: 0.1)
        XCTAssertEqual(volumes(in: built, at: 3), [0, 1])
    }

    func testACutInsideTheSelectionTrimsTheClipAndStillBuilds() async throws {
        try await writeMedia()
        let edit = try document(clipSeconds: 5).applying(.removeRange(TimeSpan(start: 2.5, end: 3.5)))
        let built = try await build(edit, clips: [edit.speechReplacements[0].id: speechClip])

        XCTAssertEqual(Timeline.seconds(built.duration), 8, accuracy: 0.1)
        let video = try await coverage(built, .video)
        XCTAssertEqual(video[0].gaps, 0)
    }

    func testMutingTheVoiceLaneMutesTheNewSpeechToo() async throws {
        try await writeMedia()
        let edit = try document(clipSeconds: 5).applying(.setLaneMuted(lane: .microphone, muted: true))
        let built = try await build(edit, clips: [edit.speechReplacements[0].id: speechClip])

        XCTAssertEqual(volumes(in: built, at: 3), [0, 0])
    }
}
