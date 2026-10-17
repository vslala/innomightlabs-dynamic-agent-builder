import XCTest
@testable import Aura

final class FeatureFlagsTests: XCTestCase {
    private let key = "Aura.wakeWordListenerEnabled"
    private var original: Bool!
    private let browserKey = "Aura.browserDemoEnabled"
    private var originalBrowserValue: Any?

    override func setUpWithError() throws {
        original = UserDefaults.standard.bool(forKey: key)
        originalBrowserValue = UserDefaults.standard.object(forKey: browserKey)
    }

    override func tearDownWithError() throws {
        UserDefaults.standard.set(original, forKey: key)
        if let originalBrowserValue {
            UserDefaults.standard.set(originalBrowserValue, forKey: browserKey)
        } else {
            UserDefaults.standard.removeObject(forKey: browserKey)
        }
    }

    func testWakeWordListenerIsOffUnlessExplicitlyEnabled() {
        UserDefaults.standard.removeObject(forKey: key)

        XCTAssertFalse(
            FeatureFlags.isWakeWordListenerEnabled,
            "always-on listening must never be the default — it holds the microphone open for the life of the app"
        )
    }

    func testBrowserDemoIsEnabledWithoutAStoredPreference() {
        UserDefaults.standard.removeObject(forKey: browserKey)
        XCTAssertTrue(FeatureFlags.isBrowserDemoEnabled)
    }

    func testBrowserDemoRespectsExplicitPreference() {
        FeatureFlags.isBrowserDemoEnabled = false
        XCTAssertFalse(FeatureFlags.isBrowserDemoEnabled)
        FeatureFlags.isBrowserDemoEnabled = true
        XCTAssertTrue(FeatureFlags.isBrowserDemoEnabled)
    }

    func testFlagRoundTrips() {
        FeatureFlags.isWakeWordListenerEnabled = true
        XCTAssertTrue(FeatureFlags.isWakeWordListenerEnabled)

        FeatureFlags.isWakeWordListenerEnabled = false
        XCTAssertFalse(FeatureFlags.isWakeWordListenerEnabled)
    }
}
