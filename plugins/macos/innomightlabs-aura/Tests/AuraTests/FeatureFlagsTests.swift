import XCTest
@testable import Aura

final class FeatureFlagsTests: XCTestCase {
    private let key = "Aura.wakeWordListenerEnabled"
    private var original: Bool!

    override func setUpWithError() throws {
        original = UserDefaults.standard.bool(forKey: key)
    }

    override func tearDownWithError() throws {
        UserDefaults.standard.set(original, forKey: key)
    }

    func testWakeWordListenerIsOffUnlessExplicitlyEnabled() {
        UserDefaults.standard.removeObject(forKey: key)

        XCTAssertFalse(
            FeatureFlags.isWakeWordListenerEnabled,
            "always-on listening must never be the default — it holds the microphone open for the life of the app"
        )
    }

    func testFlagRoundTrips() {
        FeatureFlags.isWakeWordListenerEnabled = true
        XCTAssertTrue(FeatureFlags.isWakeWordListenerEnabled)

        FeatureFlags.isWakeWordListenerEnabled = false
        XCTAssertFalse(FeatureFlags.isWakeWordListenerEnabled)
    }
}
