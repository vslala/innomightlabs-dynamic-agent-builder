import XCTest
import CoreMedia
@testable import Aura

final class PauseClockTests: XCTestCase {
    func testNoPauseIsPassthrough() {
        let clock = PauseClock()
        let time = CMTime(seconds: 5, preferredTimescale: 600)
        XCTAssertEqual(clock.adjustedTime(for: time), time)
    }

    func testSampleDuringPauseIsDropped() {
        let clock = PauseClock()
        clock.pause(at: CMTime(seconds: 1, preferredTimescale: 600))
        let sampleDuringPause = CMTime(seconds: 1.5, preferredTimescale: 600)
        XCTAssertNil(clock.adjustedTime(for: sampleDuringPause))
    }

    func testSampleAfterResumeIsRebasedByPausedDuration() {
        let clock = PauseClock()
        clock.pause(at: CMTime(seconds: 10, preferredTimescale: 600))
        clock.resume(at: CMTime(seconds: 12, preferredTimescale: 600)) // 2s paused

        let sampleAfterResume = CMTime(seconds: 15, preferredTimescale: 600)
        let adjusted = clock.adjustedTime(for: sampleAfterResume)

        XCTAssertEqual(adjusted, CMTime(seconds: 13, preferredTimescale: 600))
    }

    func testMultiplePauseResumeCyclesAccumulate() {
        let clock = PauseClock()

        clock.pause(at: CMTime(seconds: 5, preferredTimescale: 600))
        clock.resume(at: CMTime(seconds: 7, preferredTimescale: 600)) // +2s

        clock.pause(at: CMTime(seconds: 20, preferredTimescale: 600))
        clock.resume(at: CMTime(seconds: 25, preferredTimescale: 600)) // +5s

        let sample = CMTime(seconds: 30, preferredTimescale: 600)
        XCTAssertEqual(clock.adjustedTime(for: sample), CMTime(seconds: 23, preferredTimescale: 600))
    }

    func testResumeWithoutPauseIsNoOp() {
        let clock = PauseClock()
        clock.resume(at: CMTime(seconds: 1, preferredTimescale: 600))
        let sample = CMTime(seconds: 2, preferredTimescale: 600)
        XCTAssertEqual(clock.adjustedTime(for: sample), sample)
    }

    func testIsPausedReflectsState() {
        let clock = PauseClock()
        XCTAssertFalse(clock.isPaused)
        clock.pause(at: CMTime(seconds: 1, preferredTimescale: 600))
        XCTAssertTrue(clock.isPaused)
        clock.resume(at: CMTime(seconds: 2, preferredTimescale: 600))
        XCTAssertFalse(clock.isPaused)
    }

    /// A clock seeded with paused time already elapsed — the shape a writer added by a live
    /// profile switch after an earlier pause/resume needs — must rebase identically to one
    /// that accumulated the same duration live. A writer seeded at zero instead would land its
    /// track later than the writers that were already running, by exactly the seeded amount.
    func testSeededClockRebasesIdenticallyToOneThatAccumulatedLive() {
        let seeded = PauseClock(accumulatedPausedDuration: CMTime(seconds: 2, preferredTimescale: 600))

        let live = PauseClock()
        live.pause(at: CMTime(seconds: 10, preferredTimescale: 600))
        live.resume(at: CMTime(seconds: 12, preferredTimescale: 600)) // +2s, matching the seed

        let sample = CMTime(seconds: 20, preferredTimescale: 600)
        XCTAssertEqual(seeded.adjustedTime(for: sample), live.adjustedTime(for: sample))
    }

    func testSeededClockWithNoFurtherPausesStillSubtractsTheSeed() {
        let clock = PauseClock(accumulatedPausedDuration: CMTime(seconds: 5, preferredTimescale: 600))
        let sample = CMTime(seconds: 8, preferredTimescale: 600)
        XCTAssertEqual(clock.adjustedTime(for: sample), CMTime(seconds: 3, preferredTimescale: 600))
    }
}
