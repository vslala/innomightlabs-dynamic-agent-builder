import AVFoundation
import CoreMedia
import XCTest
@testable import Aura

final class MicrophoneSignalMonitorTests: XCTestCase {
    private let sampleRate = 48_000.0
    /// 10 ms, about what a capture buffer carries.
    private let chunkFrames = 480

    /// Feeds `seconds` of signal, where `sample(t)` gives the value at time `t`, and returns
    /// every problem reported along with when.
    private func feed(
        _ monitor: inout MicrophoneSignalMonitor,
        seconds: Double,
        from start: Double = 0,
        sample: (Double) -> Double
    ) -> [(time: Double, problem: MicrophoneSignalMonitor.Problem)] {
        var reported: [(Double, MicrophoneSignalMonitor.Problem)] = []
        var frame = Int(start * sampleRate)
        let end = Int((start + seconds) * sampleRate)
        while frame < end {
            var chunk = SignalChunk(sum: 0, sumOfSquares: 0, sampleCount: chunkFrames, duration: Double(chunkFrames) / sampleRate)
            for index in 0..<chunkFrames {
                let value = sample(Double(frame + index) / sampleRate)
                chunk.sum += value
                chunk.sumOfSquares += value * value
            }
            frame += chunkFrames
            if let problem = monitor.ingest(chunk) {
                reported.append((Double(frame) / sampleRate, problem))
            }
        }
        return reported
    }

    /// Deterministic noise in -1...1, so the tests never flake.
    private func noise(_ t: Double) -> Double {
        let x = sin(t * 12_345.678) * 43_758.5453
        return (x - x.rounded(.down)) * 2 - 1
    }

    /// Narration: 600 ms of loud speech-band tone, then a 500 ms breath of quiet room tone —
    /// long enough to hold one whole 250 ms block wherever the block boundaries fall.
    private func narration(_ t: Double) -> Double {
        let speaking = t.truncatingRemainder(dividingBy: 1.1) < 0.6
        return speaking ? 0.3 * sin(2 * .pi * 220 * t) : 0.001 * noise(t)
    }

    func testNarrationWithPausesIsNeverFlagged() {
        var monitor = MicrophoneSignalMonitor()
        XCTAssertTrue(feed(&monitor, seconds: 60, sample: narration).isEmpty)
    }

    func testSilenceIsNeverFlagged() {
        var monitor = MicrophoneSignalMonitor()
        XCTAssertTrue(feed(&monitor, seconds: 30) { _ in 0 }.isEmpty)
    }

    func testRelentlessNoiseLikeTheBrokenFifineIsFlaggedWithinOneWindow() throws {
        // The broken take: noise around -13 dBFS that never drops, whatever the speaker does.
        var monitor = MicrophoneSignalMonitor()
        let reported = feed(&monitor, seconds: 20) { self.noise($0) * 0.4 }

        let first = try XCTUnwrap(reported.first)
        guard case .noiseFloor(let dBFS) = first.problem else { return XCTFail("expected a noise-floor problem") }
        XCTAssertGreaterThan(dBFS, MicrophoneSignalMonitor.noiseFloorThresholdDBFS)
        XCTAssertLessThan(first.time, 6.5, "should warn as soon as one window has been seen")
    }

    func testDCOffsetIsFlaggedEvenWhenQuiet() throws {
        var monitor = MicrophoneSignalMonitor()
        let reported = feed(&monitor, seconds: 10) { -0.04 + 0.001 * self.noise($0) }

        let first = try XCTUnwrap(reported.first)
        guard case .dcOffset(let offset) = first.problem else { return XCTFail("expected a DC-offset problem") }
        XCTAssertEqual(offset, -0.04, accuracy: 0.002)
    }

    func testReportsOnceNotOncePerWindow() {
        var monitor = MicrophoneSignalMonitor()
        XCTAssertEqual(feed(&monitor, seconds: 60) { self.noise($0) * 0.4 }.count, 1)
    }

    func testCorruptionStartingMidTakeIsCaught() throws {
        var monitor = MicrophoneSignalMonitor()
        XCTAssertTrue(feed(&monitor, seconds: 30, sample: narration).isEmpty)

        let reported = feed(&monitor, seconds: 15, from: 30) { self.noise($0) * 0.4 }
        let first = try XCTUnwrap(reported.first)
        XCTAssertLessThan(first.time, 30 + 6.5)
    }

    // MARK: - Reading capture buffers

    func testReadsSixteenBitIntegerBuffers() throws {
        // The Fifine's native format.
        let chunk = try XCTUnwrap(SignalChunk(try makeBuffer(samples: [16_384, -16_384, 16_384, -16_384], float: false)))

        XCTAssertEqual(chunk.sampleCount, 4)
        XCTAssertEqual(chunk.sum, 0, accuracy: 1e-9)
        XCTAssertEqual(chunk.sumOfSquares, 1.0, accuracy: 1e-9) // four samples of ±0.5
        XCTAssertEqual(chunk.duration, 4 / sampleRate, accuracy: 1e-12)
    }

    func testReadsFloatBuffers() throws {
        let chunk = try XCTUnwrap(SignalChunk(try makeBuffer(samples: [0.25, 0.25, 0.25, 0.25], float: true)))

        XCTAssertEqual(chunk.sampleCount, 4)
        XCTAssertEqual(chunk.sum, 1.0, accuracy: 1e-6)
        XCTAssertEqual(chunk.sumOfSquares, 0.25, accuracy: 1e-6)
    }

    func testDescribesTheDeliveredFormat() {
        var asbd = AudioStreamBasicDescription(
            mSampleRate: 48_000, mFormatID: kAudioFormatLinearPCM,
            mFormatFlags: kAudioFormatFlagIsSignedInteger | kAudioFormatFlagIsPacked,
            mBytesPerPacket: 2, mFramesPerPacket: 1, mBytesPerFrame: 2,
            mChannelsPerFrame: 1, mBitsPerChannel: 16, mReserved: 0
        )
        XCTAssertEqual(AudioFormatSummary.describe(asbd), "48000 Hz, 1 ch, 16-bit integer, interleaved")

        asbd.mFormatFlags = kAudioFormatFlagIsFloat | kAudioFormatFlagIsNonInterleaved
        asbd.mBitsPerChannel = 32
        asbd.mChannelsPerFrame = 2
        XCTAssertEqual(AudioFormatSummary.describe(asbd), "48000 Hz, 2 ch, 32-bit float, non-interleaved")
    }

    /// A mono linear-PCM sample buffer, the shape `AVCaptureAudioDataOutput` delivers.
    private func makeBuffer(samples: [Double], float: Bool) throws -> CMSampleBuffer {
        let bytesPerSample = float ? 4 : 2
        var asbd = AudioStreamBasicDescription(
            mSampleRate: sampleRate, mFormatID: kAudioFormatLinearPCM,
            mFormatFlags: (float ? kAudioFormatFlagIsFloat : kAudioFormatFlagIsSignedInteger) | kAudioFormatFlagIsPacked,
            mBytesPerPacket: UInt32(bytesPerSample), mFramesPerPacket: 1, mBytesPerFrame: UInt32(bytesPerSample),
            mChannelsPerFrame: 1, mBitsPerChannel: UInt32(bytesPerSample * 8), mReserved: 0
        )
        var format: CMAudioFormatDescription?
        XCTAssertEqual(CMAudioFormatDescriptionCreate(
            allocator: nil, asbd: &asbd, layoutSize: 0, layout: nil,
            magicCookieSize: 0, magicCookie: nil, extensions: nil, formatDescriptionOut: &format
        ), noErr)

        let data: Data = float
            ? samples.map { Float32($0) }.withUnsafeBytes { Data($0) }
            : samples.map { Int16($0) }.withUnsafeBytes { Data($0) }

        var block: CMBlockBuffer?
        XCTAssertEqual(CMBlockBufferCreateWithMemoryBlock(
            allocator: nil, memoryBlock: nil, blockLength: data.count, blockAllocator: nil,
            customBlockSource: nil, offsetToData: 0, dataLength: data.count, flags: 0, blockBufferOut: &block
        ), noErr)
        let blockBuffer = try XCTUnwrap(block)
        _ = data.withUnsafeBytes { bytes in
            CMBlockBufferReplaceDataBytes(with: bytes.baseAddress!, blockBuffer: blockBuffer, offsetIntoDestination: 0, dataLength: data.count)
        }

        var sampleBuffer: CMSampleBuffer?
        XCTAssertEqual(CMAudioSampleBufferCreateReadyWithPacketDescriptions(
            allocator: nil, dataBuffer: blockBuffer, formatDescription: try XCTUnwrap(format),
            sampleCount: samples.count, presentationTimeStamp: .zero, packetDescriptions: nil,
            sampleBufferOut: &sampleBuffer
        ), noErr)
        return try XCTUnwrap(sampleBuffer)
    }
}
