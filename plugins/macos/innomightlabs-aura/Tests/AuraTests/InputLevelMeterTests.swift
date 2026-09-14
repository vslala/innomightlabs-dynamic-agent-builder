import XCTest
@testable import Aura

final class InputLevelMeterTests: XCTestCase {
    private let meter = InputLevelMeter()

    func testFullScaleIsOneAndSilenceIsZero() {
        XCTAssertEqual(meter.normalized(dbFS: 0), 1, accuracy: 0.0001)
        XCTAssertEqual(meter.normalized(dbFS: InputLevelMeter.floor), 0, accuracy: 0.0001)
    }

    func testNormalizedIsMonotonicBetweenFloorAndZero() {
        let quiet = meter.normalized(dbFS: -40)
        let loud = meter.normalized(dbFS: -20)
        XCTAssertTrue((0...1).contains(quiet))
        XCTAssertTrue((0...1).contains(loud))
        XCTAssertLessThan(quiet, loud)
    }

    func testAttackMovesFasterThanDecay() {
        // Same magnitude of change in both directions: attack (rising) should move further in
        // one step than decay (falling).
        let rising = meter.smoothed(previous: 0, next: 1)
        let falling = meter.smoothed(previous: 1, next: 0)
        XCTAssertGreaterThan(rising, 1 - falling)
    }

    func testNonFiniteRMSDoesNotEscapeAsANonFiniteLevel() {
        for input in [Double.nan, .infinity, -.infinity, 0, -1] {
            let db = meter.dbFS(rms: input)
            XCTAssertTrue(db.isFinite, "dbFS(rms: \(input)) was not finite")

            let level = meter.normalized(dbFS: db)
            XCTAssertTrue(level.isFinite, "normalized(dbFS:) from rms \(input) was not finite")
            XCTAssertTrue((0...1).contains(level))
        }
    }

    func testNormalizedOfANonFiniteInputIsSilence() {
        XCTAssertEqual(meter.normalized(dbFS: .nan), 0)
        XCTAssertEqual(meter.normalized(dbFS: .infinity), 0)
    }

    func testFullScaleRMSReachesZeroDBFS() {
        XCTAssertEqual(meter.dbFS(rms: 1), 0, accuracy: 0.0001)
    }
}
