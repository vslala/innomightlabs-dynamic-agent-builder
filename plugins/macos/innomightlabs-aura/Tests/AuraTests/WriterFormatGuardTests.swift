import AVFoundation
import XCTest
@testable import Aura

final class WriterFormatGuardTests: XCTestCase {
    private let int16 = "48000 Hz, 1 ch, 16-bit integer, interleaved"
    private let float32 = "48000 Hz, 1 ch, 32-bit float, non-interleaved"

    func testTheFirstFormatIsEstablishedAndKept() {
        var formatGuard = WriterFormatGuard()
        XCTAssertEqual(formatGuard.admit(int16), .write)
        XCTAssertEqual(formatGuard.admit(int16), .write)
        XCTAssertEqual(formatGuard.established, int16)
    }

    func testAMidTakeSwitchIsDroppedNotWritten() {
        // The switch that corrupted 20261008-023721-ea5b: the writer would have misread every
        // buffer from here on.
        var formatGuard = WriterFormatGuard()
        XCTAssertEqual(formatGuard.admit(int16), .write)
        XCTAssertEqual(formatGuard.admit(float32), .drop(isFirstMismatch: true))
        XCTAssertEqual(formatGuard.admit(float32), .drop(isFirstMismatch: false))
        XCTAssertEqual(formatGuard.established, int16)
    }

    func testSwitchingBackResumesWriting() {
        var formatGuard = WriterFormatGuard()
        _ = formatGuard.admit(int16)
        _ = formatGuard.admit(float32)
        XCTAssertEqual(formatGuard.admit(int16), .write)
        XCTAssertEqual(formatGuard.admit(float32), .drop(isFirstMismatch: false), "the change is reported only once")
    }

    func testAnUnreadableFormatIsNotTreatedAsAChange() {
        var formatGuard = WriterFormatGuard()
        XCTAssertEqual(formatGuard.admit(nil), .write)
        XCTAssertNil(formatGuard.established)
        XCTAssertEqual(formatGuard.admit(int16), .write)
        XCTAssertEqual(formatGuard.admit(nil), .write)
    }

    func testCaptureIsPinnedToOneFormat() {
        // Unpinned, the capture output passes through whatever the audio system produces,
        // which is what changed mid-take.
        let settings = MicrophoneCaptureSource.captureAudioSettings
        XCTAssertEqual(settings[AVFormatIDKey] as? AudioFormatID, kAudioFormatLinearPCM)
        XCTAssertEqual(settings[AVLinearPCMIsFloatKey] as? Bool, true)
        XCTAssertEqual(settings[AVLinearPCMBitDepthKey] as? Int, 32)
        XCTAssertEqual(settings[AVLinearPCMIsNonInterleaved] as? Bool, false)
        XCTAssertEqual(settings[AVNumberOfChannelsKey] as? Int, 1)
        XCTAssertEqual(settings[AVSampleRateKey] as? Int, 48_000)
    }
}
