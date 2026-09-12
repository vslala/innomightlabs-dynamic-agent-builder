import XCTest
@testable import Aura

final class CommandPaletteTests: XCTestCase {
    func testEmptyQueryReturnsEverything() {
        XCTAssertEqual(CommandPalette.matching("").count, CommandPalette.all.count)
        XCTAssertEqual(CommandPalette.matching("   ").count, CommandPalette.all.count)
    }

    func testExactTitleMatchRanksFirst() {
        XCTAssertEqual(CommandPalette.matching("Export").first?.id, "export")
    }

    /// A palette user expects this: typing the initials of a phrase should find it.
    func testSubsequenceMatching() {
        XCTAssertEqual(CommandPalette.matching("rmsil").first?.id, "remove-silences")
        XCTAssertEqual(CommandPalette.matching("splt").first?.id, "split")
    }

    func testKeywordsFindCommandsTheTitleDoesNot() {
        // "pauses" appears nowhere in "Remove silences".
        XCTAssertEqual(CommandPalette.matching("pauses").first?.id, "remove-silences")
        XCTAssertEqual(CommandPalette.matching("razor").first?.id, "blade")
        XCTAssertEqual(CommandPalette.matching("srt").first?.id, "generate-captions")
    }

    func testTitleMatchesOutrankKeywordMatches() {
        // "Camera only" has the word in its title; other commands only mention it in keywords.
        let results = CommandPalette.matching("camera")
        XCTAssertEqual(results.first?.id, "layout-camera")
    }

    /// Regression: "srt" is a subsequence of "Shorten" (s·h·o·r·t), which outranked the command
    /// whose keywords literally contain "srt". Exactness has to dominate fuzziness.
    func testAnExactKeywordBeatsAScatteredTitleSubsequence() {
        XCTAssertEqual(CommandPalette.matching("srt").first?.id, "generate-captions")
    }

    func testAnExactTitleBeatsEverything() {
        XCTAssertEqual(CommandPalette.matching("Blade tool").first?.id, "blade")
    }

    func testAPrefixBeatsAScatteredSubsequence() {
        // "exp" starts "Export…"; it is only scattered elsewhere.
        XCTAssertEqual(CommandPalette.matching("exp").first?.id, "export")
    }

    func testNoMatchReturnsEmpty() {
        XCTAssertTrue(CommandPalette.matching("zzzzqqq").isEmpty)
    }

    func testSearchIsCaseInsensitive() {
        XCTAssertEqual(
            CommandPalette.matching("EXPORT").map(\.id),
            CommandPalette.matching("export").map(\.id)
        )
    }

    // MARK: - Registry integrity

    func testIdsAreUnique() {
        let ids = CommandPalette.all.map(\.id)
        XCTAssertEqual(Set(ids).count, ids.count)
    }

    /// The panel's cards and the palette should not drift: an action added to one without the
    /// other is invisible from that surface. Unavailable actions are the deliberate exception —
    /// a palette is for doing things, so offering one that cannot run would be noise.
    func testEveryAvailableStudioActionIsReachableFromThePalette() {
        let exposed = Set(CommandPalette.all.compactMap { command -> StudioAction? in
            if case .studio(let action) = command.action { return action }
            return nil
        })

        for action in StudioAction.allCases {
            if case .unavailable = action.kind {
                XCTAssertFalse(
                    exposed.contains(action),
                    "\(action.rawValue) cannot run, so it should not be in the palette"
                )
            } else {
                XCTAssertTrue(exposed.contains(action), "\(action.rawValue) is missing from the palette")
            }
        }
    }

    func testEveryLayoutModeIsReachable() {
        let exposed = Set(CommandPalette.all.compactMap { command -> LayoutMode? in
            if case .layout(let mode) = command.action { return mode }
            return nil
        })
        XCTAssertEqual(exposed, Set(LayoutMode.allCases))
    }

    func testTitlesAreNotEmpty() {
        for command in CommandPalette.all {
            XCTAssertFalse(command.title.isEmpty, "\(command.id) has no title")
        }
    }
}
