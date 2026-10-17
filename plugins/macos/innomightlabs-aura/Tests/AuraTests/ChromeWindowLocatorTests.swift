import XCTest
@testable import Aura

final class ChromeWindowLocatorTests: XCTestCase {
    private func window(_ id: UInt32, pid: Int32 = 42, width: Double = 1440, height: Double = 900,
                        onScreen: Bool = true, layer: Int = 0) -> ChromeWindowLocator.Candidate {
        .init(windowID: id, processID: pid, frame: CGRect(x: -1440, y: 25, width: width, height: height),
              isOnScreen: onScreen, windowLayer: layer)
    }

    func testSelectsOnlyRequestedPIDAndSizeNotAnotherChromeWindow() throws {
        let id = try ChromeWindowLocator.selectWindowID(
            from: [window(1, pid: 99), window(2, width: 800), window(3), window(4, layer: 1), window(5, onScreen: false)],
            processID: 42, requestedSize: .init(width: 1440, height: 900))
        XCTAssertEqual(id, 3)
    }

    func testSmallWindowManagerRoundingIsAccepted() throws {
        XCTAssertEqual(try ChromeWindowLocator.selectWindowID(from: [window(1, width: 1438, height: 904)], processID: 42,
                                                              requestedSize: .init(width: 1440, height: 900)), 1)
    }

    func testMissingWindowDoesNotFallBackToAnotherProcess() {
        XCTAssertThrowsError(try ChromeWindowLocator.selectWindowID(from: [window(1, pid: 99)], processID: 42,
                                                                    requestedSize: .init(width: 1440, height: 900))) {
            XCTAssertEqual($0 as? ChromeWindowLocator.LocatorError, .notFound)
        }
    }

    func testAmbiguousWindowsFailRatherThanPickingArbitrarily() {
        XCTAssertThrowsError(try ChromeWindowLocator.selectWindowID(from: [window(1), window(2)], processID: 42,
                                                                    requestedSize: .init(width: 1440, height: 900))) {
            XCTAssertEqual($0 as? ChromeWindowLocator.LocatorError, .ambiguous)
        }
    }

    func testInvalidRequestIsRejected() {
        for pid: Int32 in [0, -1] {
            XCTAssertThrowsError(try ChromeWindowLocator.selectWindowID(from: [], processID: pid,
                                                                        requestedSize: .init(width: 1440, height: 900))) {
                XCTAssertEqual($0 as? ChromeWindowLocator.LocatorError, .invalidRequest)
            }
        }
        XCTAssertThrowsError(try ChromeWindowLocator.selectWindowID(from: [], processID: 42,
                                                                    requestedSize: .init(width: 0, height: 900)))
        XCTAssertThrowsError(try ChromeWindowLocator.selectWindowID(from: [], processID: 42,
                                                                    requestedSize: .init(width: 1440, height: 900), tolerance: .nan))
    }
}
