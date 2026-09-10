import XCTest
@testable import Aura

final class PeaksCacheTests: XCTestCase {
    private let stamp = PeaksCache.SourceStamp(size: 4096, modified: 1_700_000_000_000)

    private var peaks: WaveformPeaks {
        WaveformPeaks(
            bucketsPerSecond: 100,
            minima: [-0.5, 0, -1],
            maxima: [0.5, 0, 1],
            coverage: [true, false, true]
        )
    }

    func testRoundTripsThroughTheBinaryFormat() {
        let data = PeaksCache.encode(peaks, stamp: stamp)

        XCTAssertEqual(PeaksCache.decode(data, expecting: stamp), peaks)
    }

    func testStaleSourceStampIsRejected() {
        // Re-recording into the same path must not reuse the previous waveform.
        let data = PeaksCache.encode(peaks, stamp: stamp)
        let different = PeaksCache.SourceStamp(size: 4096, modified: 1_700_000_999_000)

        XCTAssertNil(PeaksCache.decode(data, expecting: different))
    }

    func testDifferentFileSizeIsRejected() {
        let data = PeaksCache.encode(peaks, stamp: stamp)
        let different = PeaksCache.SourceStamp(size: 9999, modified: stamp.modified)

        XCTAssertNil(PeaksCache.decode(data, expecting: different))
    }

    func testTruncatedBlobIsRejectedRatherThanPartiallyRead() {
        let data = PeaksCache.encode(peaks, stamp: stamp)

        for length in [0, 4, 8, 20, data.count - 1] {
            XCTAssertNil(
                PeaksCache.decode(data.prefix(length), expecting: stamp),
                "A \(length)-byte blob should not decode"
            )
        }
    }

    func testForeignDataIsRejected() {
        XCTAssertNil(PeaksCache.decode(Data(repeating: 0xAB, count: 128), expecting: stamp))
    }

    func testBinaryFormatIsCompactRelativeToJSON() {
        // The reason this is binary at all: it is a UI cache nobody reads, and a
        // half-hour lane is ~180k buckets.
        let big = WaveformPeaks(
            bucketsPerSecond: 100,
            minima: Array(repeating: -0.5, count: 180_000),
            maxima: Array(repeating: 0.5, count: 180_000),
            coverage: Array(repeating: true, count: 180_000)
        )

        let data = PeaksCache.encode(big, stamp: stamp)

        XCTAssertLessThan(data.count, 3_000_000)
        XCTAssertEqual(PeaksCache.decode(data, expecting: stamp)?.bucketCount, 180_000)
    }

    func testStoreAndLoadThroughTheFilesystem() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-peaks-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let source = directory.appendingPathComponent("microphone.m4a")
        let cache = directory.appendingPathComponent("microphone.peaks")
        try Data(repeating: 7, count: 2048).write(to: source)

        PeaksCache.store(peaks, cacheURL: cache, sourceURL: source)
        XCTAssertEqual(PeaksCache.load(cacheURL: cache, sourceURL: source), peaks)

        // Rewriting the source invalidates the cache.
        try Data(repeating: 9, count: 4096).write(to: source)
        XCTAssertNil(PeaksCache.load(cacheURL: cache, sourceURL: source))
    }

    func testEmptyPeaksAreNotCached() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-peaks-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let source = directory.appendingPathComponent("microphone.m4a")
        let cache = directory.appendingPathComponent("microphone.peaks")
        try Data(repeating: 7, count: 16).write(to: source)

        PeaksCache.store(.empty, cacheURL: cache, sourceURL: source)

        XCTAssertFalse(FileManager.default.fileExists(atPath: cache.path))
    }
}
