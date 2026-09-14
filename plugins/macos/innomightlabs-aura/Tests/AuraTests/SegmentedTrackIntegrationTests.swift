import XCTest
import AVFoundation
import CoreMedia
@testable import Aura

/// Hand-builds a session folder with a track recorded as two on-windows ("segments") — the
/// shape a live profile switch produces — using real, AVFoundation-parseable audio files
/// rather than fakes. This is where the claim the whole design rests on gets proven rather
/// than assumed: that `SourceTrackProbe.probeAll` and `TimelineResolver` already place a
/// multi-file track correctly, with no new composition-layer concept required.
final class SegmentedTrackIntegrationTests: XCTestCase {
    private var sessionDirectory: URL!

    override func setUpWithError() throws {
        sessionDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-segment-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: sessionDirectory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: sessionDirectory)
    }

    /// A real, decodable AAC file of silence — the same container and codec
    /// `TrackSpec.audio` configures `TrackWriter` to produce.
    private func writeSilentAudio(to url: URL, seconds: Double) throws {
        let sampleRate = 44_100.0
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatMPEG4AAC,
            AVSampleRateKey: sampleRate,
            AVNumberOfChannelsKey: 1
        ]
        let file = try AVAudioFile(forWriting: url, settings: settings)
        let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 1)!
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(sampleRate * seconds))!
        buffer.frameLength = buffer.frameCapacity // zero-filled by allocation: silence
        try file.write(from: buffer)
    }

    private func writeEvents(_ events: [RecordingEvent], to folder: SessionFolder) throws {
        let lines = try events.map { event -> String in
            String(data: try JSONEncoder().encode(event), encoding: .utf8)!
        }
        try lines.joined(separator: "\n").write(to: folder.eventsURL, atomically: true, encoding: .utf8)
    }

    /// Two on-windows of the microphone — as if the user paused, switched away and back,
    /// though which profile caused it does not matter here — probing as two segments in
    /// ascending order, each with its own recorded offset applied.
    func testTwoSegmentsOfTheSameKindProbeIndependentlyWithTheirOwnOffsets() async throws {
        let folder = SessionFolder.make(date: Date(timeIntervalSince1970: 0), suffix: "seg1", baseDirectory: sessionDirectory)
        try FileManager.default.createDirectory(at: folder.rootURL, withIntermediateDirectories: true)

        try writeSilentAudio(to: folder.url(for: .microphone, segment: 0), seconds: 2.0)
        try writeSilentAudio(to: folder.url(for: .microphone, segment: 1), seconds: 1.5)
        try writeEvents([
            RecordingEvent(ts: 0.02, type: .trackStart, mediaTs: 0.02, label: "microphone", path: "microphone.m4a"),
            RecordingEvent(ts: 5.3, type: .trackStart, mediaTs: 5.3, label: "microphone", path: "microphone-1.m4a")
        ], to: folder)

        let probes = await SourceTrackProbe.probeAll(in: folder)
        let micProbes = probes.filter { $0.kind == .microphone }

        XCTAssertEqual(micProbes.count, 2)
        XCTAssertEqual(micProbes[0].url.lastPathComponent, "microphone.m4a")
        XCTAssertEqual(micProbes[1].url.lastPathComponent, "microphone-1.m4a")
        XCTAssertEqual(Timeline.seconds(micProbes[0].recordedStartOffset), 0.02, accuracy: 0.0001)
        XCTAssertEqual(Timeline.seconds(micProbes[1].recordedStartOffset), 5.3, accuracy: 0.0001)
    }

    /// The same fixture, resolved: one `ResolvedAudioLane` for the microphone carrying both
    /// segments, each placed at its own offset — proving `TimelineResolver` needed no new
    /// concept to place a track that was switched off and back on.
    func testTimelineResolverPlacesBothSegmentsOnTheSameLane() async throws {
        let folder = SessionFolder.make(date: Date(timeIntervalSince1970: 0), suffix: "seg2", baseDirectory: sessionDirectory)
        try FileManager.default.createDirectory(at: folder.rootURL, withIntermediateDirectories: true)

        try writeSilentAudio(to: folder.url(for: .microphone, segment: 0), seconds: 2.0)
        try writeSilentAudio(to: folder.url(for: .microphone, segment: 1), seconds: 1.5)
        try writeEvents([
            RecordingEvent(ts: 0, type: .trackStart, mediaTs: 0, label: "microphone", path: "microphone.m4a"),
            RecordingEvent(ts: 5.0, type: .trackStart, mediaTs: 5.0, label: "microphone", path: "microphone-1.m4a")
        ], to: folder)

        let probes = await SourceTrackProbe.probeAll(in: folder)
        let resolved = TimelineResolver.resolve(document: .initial(duration: 10), probes: probes)

        let mic = try XCTUnwrap(resolved.audio.first { $0.lane == .microphone })
        XCTAssertEqual(mic.segments.count, 2)
        XCTAssertEqual(Timeline.seconds(mic.segments[0].timeOffset), 0, accuracy: 0.0001)
        XCTAssertEqual(Timeline.seconds(mic.segments[1].timeOffset), 5.0, accuracy: 0.0001)
        // The lane-level convenience reads the first segment — what the transcript (produced
        // from only the first on-window) actually aligns against.
        XCTAssertEqual(Timeline.seconds(mic.timeOffset), 0, accuracy: 0.0001)
    }

    /// A session that never switched profiles has exactly one segment per kind, at window 0 —
    /// the pre-existing, unsegmented shape must resolve identically to before this phase.
    func testASingleSegmentResolvesExactlyAsAnUnsegmentedTrackDid() async throws {
        let folder = SessionFolder.make(date: Date(timeIntervalSince1970: 0), suffix: "seg3", baseDirectory: sessionDirectory)
        try FileManager.default.createDirectory(at: folder.rootURL, withIntermediateDirectories: true)

        try writeSilentAudio(to: folder.microphoneURL, seconds: 3.0)

        let probes = await SourceTrackProbe.probeAll(in: folder)
        XCTAssertEqual(probes.filter { $0.kind == .microphone }.count, 1)

        let resolved = TimelineResolver.resolve(document: .initial(duration: 3), probes: probes)
        let mic = try XCTUnwrap(resolved.audio.first { $0.lane == .microphone })
        XCTAssertEqual(mic.segments.count, 1)
    }
}
