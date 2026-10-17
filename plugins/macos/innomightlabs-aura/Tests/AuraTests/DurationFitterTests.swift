import XCTest
@testable import Aura

final class DurationFitterTests: XCTestCase {
    func testASmallDifferenceIsStretchedToLandExactlyOnTheSelection() {
        let fit = DurationFitter.fit(speech: 4.4, selection: 4)

        XCTAssertEqual(fit.clipDuration, 4)
        XCTAssertEqual(fit.hold, 0)
        guard case .stretch(let tempo) = fit.action else { return XCTFail("expected a stretch, got \(fit.action)") }
        XCTAssertEqual(tempo, 1.1, accuracy: 0.0001)
    }

    func testTheEdgesOfTheBandStillStretch() {
        for ratio in [0.85, 1.15, 1.0] {
            guard case .stretch = DurationFitter.fit(speech: 10 * ratio, selection: 10).action else {
                return XCTFail("\(ratio) should stretch")
            }
        }
    }

    func testMuchShorterSpeechIsPaddedNotSlowedDown() {
        let fit = DurationFitter.fit(speech: 2, selection: 4)

        XCTAssertEqual(fit.action, .pad)
        XCTAssertEqual(fit.clipDuration, 4)
        XCTAssertEqual(fit.hold, 0)
    }

    func testMuchLongerSpeechKeepsItsPaceAndHoldsThePicture() {
        let fit = DurationFitter.fit(speech: 7, selection: 4)

        XCTAssertEqual(fit.action, .hold)
        XCTAssertEqual(fit.clipDuration, 7)
        XCTAssertEqual(fit.hold, 3)
        XCTAssertFalse(fit.needsConfirmation)
    }

    func testALongHoldAsksForConfirmation() {
        XCTAssertTrue(DurationFitter.fit(speech: 20, selection: 4).needsConfirmation)
        XCTAssertFalse(DurationFitter.fit(speech: 14, selection: 4).needsConfirmation)
    }

    func testNothingToFitDoesNotDivideByZero() {
        XCTAssertEqual(DurationFitter.fit(speech: 3, selection: 0).hold, 0)
        XCTAssertEqual(DurationFitter.fit(speech: 0, selection: 3).action, .pad)
    }
}
