import XCTest
import AVFoundation
@testable import Aura

/// End-to-end cover for word-level cuts: the edit document, the built composition, and the
/// live view-model wiring, against real (synthetic) media.
///
/// These exist because a word exclusion passed every unit test while doing nothing audible.
/// The model shortened correctly and the builder cut correctly, but the transcript's clock and
/// the microphone lane's clock had drifted apart, so the cut landed next to the word rather
/// than on it. Nothing that tested one layer at a time could have caught that.
@MainActor
final class WordExclusionIntegrationTests: XCTestCase {
    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-excl-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        if let root { try? FileManager.default.removeItem(at: root) }
    }

    /// A solid-colour 6s video and 6s of silence, so there is real media to compose.
    private func writeMedia() async throws {
        let folder = SessionFolder.load(rootURL: root)

        // Video
        let videoWriter = try AVAssetWriter(outputURL: folder.screenURL, fileType: .mov)
        let videoInput = AVAssetWriterInput(mediaType: .video, outputSettings: [
            AVVideoCodecKey: AVVideoCodecType.h264,
            AVVideoWidthKey: 160, AVVideoHeightKey: 90
        ])
        videoInput.expectsMediaDataInRealTime = false
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: videoInput, sourcePixelBufferAttributes: nil)
        videoWriter.add(videoInput)
        videoWriter.startWriting()
        videoWriter.startSession(atSourceTime: .zero)

        var pixelBuffer: CVPixelBuffer?
        CVPixelBufferCreate(kCFAllocatorDefault, 160, 90, kCVPixelFormatType_32BGRA, nil, &pixelBuffer)
        let buffer = try XCTUnwrap(pixelBuffer)
        for frame in 0..<180 {   // 6s at 30fps
            while !videoInput.isReadyForMoreMediaData { try await Task.sleep(for: .milliseconds(5)) }
            adaptor.append(buffer, withPresentationTime: CMTime(value: CMTimeValue(frame), timescale: 30))
        }
        videoInput.markAsFinished()
        await videoWriter.finishWriting()

        // Audio: 6s of silent PCM into an m4a
        let audioWriter = try AVAssetWriter(outputURL: folder.microphoneURL, fileType: .m4a)
        let audioInput = AVAssetWriterInput(mediaType: .audio, outputSettings: [
            AVFormatIDKey: kAudioFormatMPEG4AAC,
            AVNumberOfChannelsKey: 1,
            AVSampleRateKey: 44_100,
            AVEncoderBitRateKey: 64_000
        ])
        audioInput.expectsMediaDataInRealTime = false
        audioWriter.add(audioInput)
        audioWriter.startWriting()
        audioWriter.startSession(atSourceTime: .zero)

        let format = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 1)!
        let chunkFrames: AVAudioFrameCount = 44_100
        for second in 0..<6 {
            let pcm = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: chunkFrames)!
            pcm.frameLength = chunkFrames
            memset(pcm.floatChannelData![0], 0, Int(chunkFrames) * 4)
            let sample = try XCTUnwrap(Self.sampleBuffer(from: pcm, at: CMTime(seconds: Double(second), preferredTimescale: 44_100)))
            while !audioInput.isReadyForMoreMediaData { try await Task.sleep(for: .milliseconds(5)) }
            audioInput.append(sample)
        }
        audioInput.markAsFinished()
        await audioWriter.finishWriting()

        try Data(#"{"ts":0,"type":"record_start","media_ts":0}"#.utf8)
            .write(to: folder.eventsURL)
    }

    private static func sampleBuffer(from pcm: AVAudioPCMBuffer, at time: CMTime) -> CMSampleBuffer? {
        var sample: CMSampleBuffer?
        var format: CMFormatDescription?
        CMAudioFormatDescriptionCreate(
            allocator: kCFAllocatorDefault,
            asbd: pcm.format.streamDescription,
            layoutSize: 0, layout: nil, magicCookieSize: 0, magicCookie: nil,
            extensions: nil, formatDescriptionOut: &format
        )
        guard let format else { return nil }

        CMSampleBufferCreate(
            allocator: kCFAllocatorDefault, dataBuffer: nil, dataReady: false,
            makeDataReadyCallback: nil, refcon: nil, formatDescription: format,
            sampleCount: CMItemCount(pcm.frameLength), sampleTimingEntryCount: 1,
            sampleTimingArray: [CMSampleTimingInfo(
                duration: CMTime(value: 1, timescale: 44_100),
                presentationTimeStamp: time,
                decodeTimeStamp: .invalid
            )],
            sampleSizeEntryCount: 0, sampleSizeArray: nil, sampleBufferOut: &sample
        )
        guard let sample else { return nil }
        CMSampleBufferSetDataBufferFromAudioBufferList(
            sample, blockBufferAllocator: kCFAllocatorDefault,
            blockBufferMemoryAllocator: kCFAllocatorDefault, flags: 0,
            bufferList: pcm.audioBufferList
        )
        return sample
    }

    private func totals(in asset: AVAsset, mediaType: AVMediaType) async throws -> [(segments: Int, duration: Double)] {
        var out: [(Int, Double)] = []
        for track in try await asset.loadTracks(withMediaType: mediaType) {
            let segments = try await track.load(.segments)
            let nonEmpty = segments.filter { !$0.isEmpty }
            let total = nonEmpty.reduce(0.0) { $0 + CMTimeGetSeconds($1.timeMapping.target.duration) }
            out.append((nonEmpty.count, total))
        }
        return out.map { (segments: $0.0, duration: $0.1) }
    }

    /// Writes a v2 transcript so the view model has real words to toggle.
    private func writeTranscript() {
        let folder = SessionFolder.load(rootURL: root)
        let words = [
            Transcript.Word(id: 0, start: 1.0, end: 1.4, text: "hello"),
            Transcript.Word(id: 1, start: 2.0, end: 2.5, text: "um"),
            Transcript.Word(id: 2, start: 3.0, end: 3.6, text: "world")
        ]
        Transcript(
            source: "microphone.m4a", engine: "test", language: "en",
            segments: [Transcript.Segment(id: 0, start: 1.0, end: 3.6, text: "hello um world", words: words)]
        ).write(to: folder.transcriptURL)
    }

    /// The live path: load the window, toggle a word, and check the player's item actually
    /// got shorter — the wiring between the store, the rebuild, and the player.
    func testTogglingAWordInTheViewModelShortensThePlayersItem() async throws {
        try await writeMedia()
        writeTranscript()

        let viewModel = ReviewViewModel(folder: SessionFolder.load(rootURL: root))
        await viewModel.load()
        XCTAssertEqual(viewModel.state, .ready)

        let before = Timeline.seconds(viewModel.duration)
        let itemBefore = CMTimeGetSeconds(viewModel.player.currentItem?.asset.duration ?? .zero)

        // Wait for the transcript to side-load, then toggle "um".
        var waited = 0
        while viewModel.transcript == nil, waited < 60 {
            try await Task.sleep(for: .milliseconds(50)); waited += 1
        }
        let word = try XCTUnwrap(viewModel.transcript?.allWords.first { $0.text == "um" })

        viewModel.toggleWord(word)
        XCTAssertTrue(viewModel.isWordExcluded(word), "strikethrough state")

        // Let the rebuild land.
        try await Task.sleep(for: .milliseconds(1500))

        let after = Timeline.seconds(viewModel.duration)
        let itemAfter = CMTimeGetSeconds(viewModel.player.currentItem?.asset.duration ?? .zero)

        XCTAssertEqual(after, before - 0.5, accuracy: 0.05, "the review timeline should shorten")
        XCTAssertEqual(itemAfter, before - 0.5, accuracy: 0.05, "THE PLAYER'S ITEM must actually be shorter")

        viewModel.close()
    }

    /// A cut has to land where the word is *heard*, not where the transcript says it is.
    ///
    /// The microphone lane is shifted later in the composition to undo its capture delay. The
    /// transcript is stamped in the raw microphone file's own clock, which does not include
    /// that shift, so the two must be reconciled — otherwise a word cut removes a neighbouring
    /// slice of audio and the word itself plays on.
    func testWordCutLandsWhereTheWordActuallyPlays() async throws {
        try await writeMedia()
        writeTranscript()

        // The recorder logs this: the mic produced its first sample 0.4s after the session
        // start, and the composition shifts the mic lane later by that much to resync it.
        let folder = SessionFolder.load(rootURL: root)
        try (#"{"ts":0,"type":"record_start","media_ts":0}"# + "\n"
             + #"{"ts":0.4,"type":"track_start","media_ts":0.4,"label":"microphone"}"# + "\n")
            .write(to: folder.eventsURL, atomically: true, encoding: .utf8)

        let probes = await SourceTrackProbe.probeAll(in: folder)
        let mic = try XCTUnwrap(probes.first { $0.kind == .microphone })
        XCTAssertEqual(Timeline.seconds(mic.alignmentCorrection), 0.4, accuracy: 0.01)

        let viewModel = ReviewViewModel(folder: folder)
        await viewModel.load()
        XCTAssertEqual(viewModel.state, .ready)

        var waited = 0
        while viewModel.transcript == nil, waited < 60 {
            try await Task.sleep(for: .milliseconds(50)); waited += 1
        }
        let word = try XCTUnwrap(viewModel.transcript?.allWords.first { $0.text == "um" })

        viewModel.toggleWord(word)

        let excluded = try XCTUnwrap(viewModel.store?.document.excludedWords.first)

        // The word's audio plays at transcript time + the mic's offset, so that is where the
        // cut has to land. Cutting at the bare transcript time removes 0.4s of the wrong audio
        // and leaves the word itself intact — which is exactly what was reported.
        XCTAssertEqual(excluded.start, word.start + 0.4, accuracy: 0.01,
                       "the cut must be shifted by the same offset the audio lane was")
        XCTAssertEqual(excluded.end, word.end + 0.4, accuracy: 0.01)

        viewModel.close()
    }

    func testExcludedWordIsActuallyCutFromAudioAndVideo() async throws {
        try await writeMedia()
        let folder = SessionFolder.load(rootURL: root)
        let probes = await SourceTrackProbe.probeAll(in: folder)
        XCTAssertFalse(probes.isEmpty)

        let duration = Timeline.seconds(probes.map(\.duration).max() ?? .zero)
        let plain = SessionEdit.initial(duration: duration)

        // Cut a 0.5s "word" out of the middle.
        let edited = try plain.applying(.excludeWords([
            ExcludedWord(id: 0, start: 2.0, end: 2.5, text: "um")
        ]))
        XCTAssertEqual(edited.duration, plain.duration - 0.5, accuracy: 0.01)

        let resolved = TimelineResolver.resolve(document: edited, probes: probes)

        let built = try await LayerInstructionCompositionBuilder().build(resolved)

        let video = try await totals(in: built.asset, mediaType: .video)
        let audio = try await totals(in: built.asset, mediaType: .audio)

        // The composition itself must be shorter, and each track must be in two pieces.
        XCTAssertEqual(Timeline.seconds(built.duration), plain.duration - 0.5, accuracy: 0.05,
                       "the composition should be shortened by the excluded word")
        for track in video + audio {
            XCTAssertEqual(track.segments, 2, "expected the track to be split around the cut")
            XCTAssertEqual(track.duration, plain.duration - 0.5, accuracy: 0.05,
                           "expected the cut to remove media, not just shift it")
        }
    }
}
