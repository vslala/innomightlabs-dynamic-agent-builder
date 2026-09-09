import XCTest
@testable import Aura

final class CaptureTargetMatchTests: XCTestCase {
    private func candidates(_ names: [String]) -> [(name: String, value: String)] {
        names.map { ($0, $0) }
    }

    func testExactCaseInsensitiveMatchWins() {
        let result = NameMatcher.bestMatch(
            for: "chrome",
            among: candidates(["Chrome", "Google Chrome Helper", "Safari"])
        )
        XCTAssertEqual(result, "Chrome")
    }

    func testSubstringMatchWhenNoExactMatch() {
        let result = NameMatcher.bestMatch(for: "chrome", among: candidates(["Google Chrome", "Safari"]))
        XCTAssertEqual(result, "Google Chrome")
    }

    func testQueryContainingCandidateNameMatches() {
        let result = NameMatcher.bestMatch(for: "please record chrome now", among: candidates(["Chrome", "Safari"]))
        XCTAssertEqual(result, "Chrome")
    }

    func testClosestLengthMatchPreferredAmongSubstringMatches() {
        let result = NameMatcher.bestMatch(
            for: "code",
            among: candidates(["Visual Studio Code", "Code", "Code Helper (Renderer)"])
        )
        XCTAssertEqual(result, "Code")
    }

    func testNoMatchReturnsNil() {
        let result = NameMatcher.bestMatch(for: "nonexistent app", among: candidates(["Chrome", "Safari"]))
        XCTAssertNil(result)
    }

    func testEmptyQueryReturnsNil() {
        let result = NameMatcher.bestMatch(for: "   ", among: candidates(["Chrome"]))
        XCTAssertNil(result)
    }

    func testEmptyCandidatesReturnsNil() {
        let result: String? = NameMatcher.bestMatch(for: "Chrome", among: [])
        XCTAssertNil(result)
    }
}
