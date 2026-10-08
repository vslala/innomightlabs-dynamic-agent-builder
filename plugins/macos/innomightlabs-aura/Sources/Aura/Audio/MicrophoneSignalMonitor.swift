import CoreMedia
import Foundation

/// Notices when the microphone is delivering something other than sound, so the user hears
/// about it while they can still replug the mic rather than after an unusable take.
///
/// Real narration always has gaps: within any few seconds there is a breath or a pause where
/// the level drops to the room's noise floor, and the waveform averages out to zero. The
/// corrupted Fifine recording that motivated this (`20261008-014652-3307`) had neither — its
/// quietest quarter-second anywhere in eleven minutes was -14 dBFS and it carried a DC offset of
/// 0.04-0.07 — while the clean recordings from the same mic never had a quiet moment above
/// -46 dBFS or an offset above 0.0001. The thresholds sit between the two with a wide margin, so
/// a loud speaker or a noisy room does not trip them; a mic emitting garbage does, within one
/// window.
struct MicrophoneSignalMonitor {
    enum Problem: Equatable {
        /// Even the quietest block in the window was this loud.
        case noiseFloor(dBFS: Double)
        /// The window's samples averaged this far from zero.
        case dcOffset(Double)

        var summary: String {
            switch self {
            case .noiseFloor(let dBFS): return String(format: "noise floor %.0f dBFS", dBFS)
            case .dcOffset(let offset): return String(format: "DC offset %.3f", offset)
            }
        }
    }

    static let blockDuration: TimeInterval = 0.25
    static let windowBlockCount = 24
    static let noiseFloorThresholdDBFS = -30.0
    static let dcOffsetThreshold = 0.01

    private struct Block {
        var sum = 0.0
        var sumOfSquares = 0.0
        var sampleCount = 0
        var duration: TimeInterval = 0
    }

    private var pending = Block()
    private var window: [Block] = []
    private var hasReported = false

    /// Feeds one capture buffer's worth of samples. Returns a problem the first time the
    /// signal looks corrupted and never again: one warning per recording is a warning,
    /// one per window would be noise of its own.
    mutating func ingest(_ chunk: SignalChunk) -> Problem? {
        guard !hasReported, chunk.sampleCount > 0 else { return nil }

        pending.sum += chunk.sum
        pending.sumOfSquares += chunk.sumOfSquares
        pending.sampleCount += chunk.sampleCount
        pending.duration += chunk.duration
        // Whole buffers, not exact block boundaries: a capture buffer is ~10-20 ms, so a block
        // runs a few percent long at most, which no threshold here is sensitive to.
        guard pending.duration >= Self.blockDuration else { return nil }

        window.append(pending)
        pending = Block()
        if window.count > Self.windowBlockCount { window.removeFirst() }
        guard window.count == Self.windowBlockCount else { return nil }

        guard let problem = Self.problem(in: window) else { return nil }
        hasReported = true
        return problem
    }

    private static func problem(in window: [Block]) -> Problem? {
        let samples = window.reduce(0) { $0 + $1.sampleCount }
        let offset = window.reduce(0) { $0 + $1.sum } / Double(samples)
        if abs(offset) > dcOffsetThreshold { return .dcOffset(offset) }

        let quietest = window.map { dBFS(meanSquare: $0.sumOfSquares / Double($0.sampleCount)) }.min() ?? -.infinity
        if quietest > noiseFloorThresholdDBFS { return .noiseFloor(dBFS: quietest) }
        return nil
    }

    private static func dBFS(meanSquare: Double) -> Double {
        10 * log10(max(meanSquare, 1e-12))
    }
}

/// One capture buffer reduced to what `MicrophoneSignalMonitor` needs, with samples
/// normalised to -1...1 whatever the device's native format.
struct SignalChunk: Equatable {
    var sum: Double
    var sumOfSquares: Double
    var sampleCount: Int
    var duration: TimeInterval
}

extension SignalChunk {
    /// Nil for formats this can't read (anything but linear PCM as Float32, Int16 or Int32),
    /// in which case the monitor simply sees nothing — it must never be the thing that breaks
    /// a recording.
    init?(_ sampleBuffer: CMSampleBuffer) {
        guard
            let description = CMSampleBufferGetFormatDescription(sampleBuffer),
            let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(description)?.pointee,
            asbd.mFormatID == kAudioFormatLinearPCM, asbd.mSampleRate > 0
        else { return nil }

        let isFloat = asbd.mFormatFlags & kAudioFormatFlagIsFloat != 0
        let bits = Int(asbd.mBitsPerChannel)
        guard (isFloat && bits == 32) || (!isFloat && (bits == 16 || bits == 32)) else { return nil }

        var listSize = 0
        guard CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer, bufferListSizeNeededOut: &listSize, bufferListOut: nil, bufferListSize: 0,
            blockBufferAllocator: nil, blockBufferMemoryAllocator: nil, flags: 0, blockBufferOut: nil
        ) == noErr else { return nil }

        let storage = UnsafeMutableRawPointer.allocate(byteCount: listSize, alignment: MemoryLayout<AudioBufferList>.alignment)
        defer { storage.deallocate() }
        let list = storage.bindMemory(to: AudioBufferList.self, capacity: 1)
        var retained: CMBlockBuffer?
        guard CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer, bufferListSizeNeededOut: nil, bufferListOut: list, bufferListSize: listSize,
            blockBufferAllocator: nil, blockBufferMemoryAllocator: nil,
            flags: kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment, blockBufferOut: &retained
        ) == noErr else { return nil }

        var sum = 0.0
        var sumOfSquares = 0.0
        var count = 0
        func accumulate(_ value: Double) {
            sum += value
            sumOfSquares += value * value
        }

        // Every channel of every buffer, interleaved or not: DC offset and loudness don't
        // care which channel a sample came from.
        for buffer in UnsafeMutableAudioBufferListPointer(list) {
            guard let data = buffer.mData else { continue }
            let bytes = Int(buffer.mDataByteSize)
            switch (isFloat, bits) {
            case (true, _):
                let samples = UnsafeBufferPointer(start: data.assumingMemoryBound(to: Float32.self), count: bytes / 4)
                samples.forEach { accumulate(Double($0)) }
                count += samples.count
            case (false, 16):
                let samples = UnsafeBufferPointer(start: data.assumingMemoryBound(to: Int16.self), count: bytes / 2)
                samples.forEach { accumulate(Double($0) / 32_768) }
                count += samples.count
            default:
                let samples = UnsafeBufferPointer(start: data.assumingMemoryBound(to: Int32.self), count: bytes / 4)
                samples.forEach { accumulate(Double($0) / 2_147_483_648) }
                count += samples.count
            }
        }

        self.init(
            sum: sum,
            sumOfSquares: sumOfSquares,
            sampleCount: count,
            duration: Double(CMSampleBufferGetNumSamples(sampleBuffer)) / asbd.mSampleRate
        )
    }
}

/// How a device's delivered audio format reads in `events.jsonl`, e.g.
/// "48000 Hz, 1 ch, 16-bit integer, interleaved".
enum AudioFormatSummary {
    static func describe(_ asbd: AudioStreamBasicDescription) -> String {
        guard asbd.mFormatID == kAudioFormatLinearPCM else {
            return String(format: "%.0f Hz, %u ch, format %u", asbd.mSampleRate, asbd.mChannelsPerFrame, asbd.mFormatID)
        }
        let kind = asbd.mFormatFlags & kAudioFormatFlagIsFloat != 0 ? "float" : "integer"
        let layout = asbd.mFormatFlags & kAudioFormatFlagIsNonInterleaved != 0 ? "non-interleaved" : "interleaved"
        return String(format: "%.0f Hz, %u ch, %u-bit %@, %@",
                      asbd.mSampleRate, asbd.mChannelsPerFrame, asbd.mBitsPerChannel, kind, layout)
    }
}
