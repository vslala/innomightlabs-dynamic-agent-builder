import AVFoundation
import XCTest
@testable import Aura

final class StudioSoundRendererTests: XCTestCase {
    private var directory: URL!
    private let sampleRate = 48_000.0

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-studio-render-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    func testRendersACopyOfTheSameLengthWithTheHissReduced() async throws {
        let source = try writeHiss(seconds: 4, channels: 1)
        let destination = directory.appendingPathComponent("hiss.studio.m4a")

        try await StudioSoundRenderer.render(source: source, to: destination)

        let original = try AVAudioFile(forReading: source)
        let cleaned = try AVAudioFile(forReading: destination)
        // Equal length is what lets the copy replace the recording without moving anything.
        XCTAssertEqual(cleaned.length, original.length)
        XCTAssertEqual(cleaned.processingFormat.sampleRate, sampleRate)
        XCTAssertLessThan(try lastSecondLevel(cleaned), try lastSecondLevel(original) / 2)
    }

    func testKeepsEveryChannel() async throws {
        let source = try writeHiss(seconds: 1, channels: 2)
        let destination = directory.appendingPathComponent("stereo.studio.m4a")

        try await StudioSoundRenderer.render(source: source, to: destination)

        XCTAssertEqual(try AVAudioFile(forReading: destination).processingFormat.channelCount, 2)
    }

    func testReportsProgressUpToOne() async throws {
        let source = try writeHiss(seconds: 3, channels: 1)
        let destination = directory.appendingPathComponent("progress.studio.m4a")
        let seen = LockedValues()

        try await StudioSoundRenderer.render(source: source, to: destination) { seen.append($0) }

        let values = seen.values
        XCTAssertEqual(values.last, 1)
        XCTAssertEqual(values, values.sorted())
    }

    func testACancelledRenderLeavesNothingBehind() async throws {
        let source = try writeHiss(seconds: 4, channels: 1)
        let destination = directory.appendingPathComponent("cancelled.studio.m4a")

        let task = Task { try await StudioSoundRenderer.render(source: source, to: destination) }
        task.cancel()
        do {
            try await task.value
            XCTFail("a cancelled render should throw")
        } catch is CancellationError {}

        XCTAssertFalse(FileManager.default.fileExists(atPath: destination.path))
        let leftovers = try FileManager.default.contentsOfDirectory(atPath: directory.path)
        XCTAssertEqual(leftovers, [source.lastPathComponent])
    }

    func testAnUnreadableSourceFailsWithoutCreatingAFile() async {
        let destination = directory.appendingPathComponent("missing.studio.m4a")
        do {
            try await StudioSoundRenderer.render(
                source: directory.appendingPathComponent("nope.m4a"),
                to: destination
            )
            XCTFail("a missing source should throw")
        } catch {}
        XCTAssertFalse(FileManager.default.fileExists(atPath: destination.path))
    }

    // MARK: - Fixtures

    /// Deterministic hiss, so a failure reproduces.
    private func writeHiss(seconds: Double, channels: Int) throws -> URL {
        let url = directory.appendingPathComponent("source-\(channels).caf")
        let format = try XCTUnwrap(AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: AVAudioChannelCount(channels)))
        let frames = AVAudioFrameCount(seconds * sampleRate)
        let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames))
        buffer.frameLength = frames

        var state: UInt64 = 0x9E37_79B9_7F4A_7C15
        for channel in 0..<channels {
            for frame in 0..<Int(frames) {
                state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
                buffer.floatChannelData![channel][frame] = (Float(state >> 40) / Float(1 << 24) * 2 - 1) * 0.02
            }
        }

        let file = try AVAudioFile(forWriting: url, settings: format.settings)
        try file.write(from: buffer)
        return url
    }

    private func lastSecondLevel(_ file: AVAudioFile) throws -> Float {
        let frames = AVAudioFrameCount(sampleRate)
        file.framePosition = file.length - AVAudioFramePosition(frames)
        let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: frames))
        try file.read(into: buffer, frameCount: frames)
        let samples = UnsafeBufferPointer(start: buffer.floatChannelData![0], count: Int(buffer.frameLength))
        return (samples.map { $0 * $0 }.reduce(0, +) / Float(samples.count)).squareRoot()
    }
}

/// Collects progress values from a `@Sendable` callback.
private final class LockedValues: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [Double] = []

    func append(_ value: Double) { lock.withLock { storage.append(value) } }
    var values: [Double] { lock.withLock { storage } }
}
