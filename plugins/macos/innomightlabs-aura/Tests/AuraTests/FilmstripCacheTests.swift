import XCTest
@testable import Aura

final class FilmstripCacheTests: XCTestCase {
    private let stamp = FilmstripCache.SourceStamp(fileSize: 12_345, modified: 1_700_000_000.5)

    private func strip(frameCount: Int = 3) -> Filmstrip {
        Filmstrip(
            interval: 2,
            frameSize: CGSize(width: 160, height: 90),
            // Distinct lengths and contents, so a mis-sliced index shows up as wrong bytes
            // rather than passing by luck.
            frames: (0..<frameCount).map { index in
                Data(repeating: UInt8(index + 1), count: 10 + index * 7)
            }
        )
    }

    func testRoundTrip() throws {
        let original = strip()
        let decoded = try XCTUnwrap(
            FilmstripCache.decode(FilmstripCache.encode(original, stamp: stamp), expecting: stamp)
        )

        XCTAssertEqual(decoded.interval, original.interval, accuracy: 0.0001)
        XCTAssertEqual(decoded.frameSize, original.frameSize)
        XCTAssertEqual(decoded.frames, original.frames, "frames must survive byte-exact")
    }

    func testEmptyStripRoundTrips() throws {
        let original = Filmstrip(interval: 2, frameSize: .zero, frames: [])
        let decoded = try XCTUnwrap(
            FilmstripCache.decode(FilmstripCache.encode(original, stamp: stamp), expecting: stamp)
        )
        XCTAssertTrue(decoded.frames.isEmpty)
    }

    // MARK: - Invalidation, which is the whole point of the header

    func testADifferentFileSizeInvalidates() {
        let data = FilmstripCache.encode(strip(), stamp: stamp)
        let changed = FilmstripCache.SourceStamp(fileSize: 999, modified: stamp.modified)
        XCTAssertNil(FilmstripCache.decode(data, expecting: changed))
    }

    func testADifferentModificationTimeInvalidates() {
        let data = FilmstripCache.encode(strip(), stamp: stamp)
        let changed = FilmstripCache.SourceStamp(fileSize: stamp.fileSize, modified: 1)
        XCTAssertNil(FilmstripCache.decode(data, expecting: changed))
    }

    func testDecodingWithoutAStampSkipsValidation() throws {
        let data = FilmstripCache.encode(strip(), stamp: stamp)
        XCTAssertNotNil(FilmstripCache.decode(data, expecting: nil))
    }

    // MARK: - Malformed input must not crash

    func testGarbageIsRejected() {
        XCTAssertNil(FilmstripCache.decode(Data("not a filmstrip".utf8), expecting: nil))
        XCTAssertNil(FilmstripCache.decode(Data(), expecting: nil))
    }

    func testTruncatedPayloadIsRejected() {
        let data = FilmstripCache.encode(strip(), stamp: stamp)
        for cut in [4, 12, 30, data.count - 5] where cut > 0 && cut < data.count {
            XCTAssertNil(
                FilmstripCache.decode(data.prefix(cut), expecting: nil),
                "a file truncated at \(cut) bytes must be rejected, not half-read"
            )
        }
    }

    func testAnAbsurdFrameCountIsRejected() {
        // Guards against a corrupt header driving a huge allocation.
        var data = FilmstripCache.encode(strip(), stamp: stamp)
        let countOffset = 4 + 2 + 8 + 8 + 8 + 4 + 4
        withUnsafeBytes(of: UInt32(10_000_000).littleEndian) { bytes in
            data.replaceSubrange(countOffset..<(countOffset + 4), with: bytes)
        }
        XCTAssertNil(FilmstripCache.decode(data, expecting: nil))
    }

    // MARK: - Frame lookup

    func testFrameIndexFromSourceTime() {
        let strip = self.strip(frameCount: 5)
        XCTAssertEqual(strip.frameIndex(atSource: 0), 0)
        XCTAssertEqual(strip.frameIndex(atSource: 1.9), 0)
        XCTAssertEqual(strip.frameIndex(atSource: 2.0), 1)
        XCTAssertEqual(strip.frameIndex(atSource: 9.9), 4)
        XCTAssertNil(strip.frameIndex(atSource: 10), "past the last frame")
        XCTAssertNil(strip.frameIndex(atSource: -1))
    }

    // MARK: - Extraction plan

    func testShortRecordingsUseTheTargetInterval() {
        let plan = Filmstrip.plan(duration: 60)
        XCTAssertEqual(plan.interval, Filmstrip.targetInterval, accuracy: 0.0001)
        XCTAssertEqual(plan.count, 30)
    }

    /// The ceiling has to spread across the whole recording. Truncating instead would leave the
    /// back half of a long session with no thumbnails at all.
    func testLongRecordingsSpreadTheFrameCeiling() {
        let duration: TimeInterval = 4 * 3600
        let plan = Filmstrip.plan(duration: duration)

        XCTAssertEqual(plan.count, Filmstrip.maxFrames)
        XCTAssertEqual(plan.interval * Double(plan.count), duration, accuracy: 1)
        XCTAssertGreaterThan(plan.interval, Filmstrip.targetInterval)
    }

    func testZeroDurationAsksForNothing() {
        XCTAssertEqual(Filmstrip.plan(duration: 0).count, 0)
    }

    func testAVeryShortRecordingStillGetsAFrame() {
        XCTAssertGreaterThanOrEqual(Filmstrip.plan(duration: 0.4).count, 1)
    }
}
