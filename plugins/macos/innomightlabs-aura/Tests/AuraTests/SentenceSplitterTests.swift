import XCTest
@testable import Aura

final class SentenceSplitterTests: XCTestCase {
    func testASingleSentenceComesBackWhole() {
        XCTAssertEqual(SentenceSplitter.split("I build things."), ["I build things."])
    }

    func testTextWithNoPunctuationIsOneSentence() {
        XCTAssertEqual(SentenceSplitter.split("just some words"), ["just some words"])
    }

    func testSplitsAtEveryKindOfSentenceEnd() {
        XCTAssertEqual(
            SentenceSplitter.split("It works. Does it? It does! Good…  Done."),
            ["It works.", "Does it?", "It does!", "Good…", "Done."]
        )
    }

    func testNewlinesAreJustSpaces() {
        XCTAssertEqual(SentenceSplitter.split("First line.\nSecond line."), ["First line.", "Second line."])
    }

    func testAFullStopWithoutASpaceAfterItIsNotTheEndOfASentence() {
        XCTAssertEqual(SentenceSplitter.split("It costs 3.5 dollars on innomight.com today."),
                       ["It costs 3.5 dollars on innomight.com today."])
    }

    func testAbbreviationsAndInitialsDoNotEndASentence() {
        XCTAssertEqual(SentenceSplitter.split("Dr. Smith met J. Doe at noon. They talked."),
                       ["Dr. Smith met J. Doe at noon.", "They talked."])
    }

    func testAQuotedNameIsNeverBrokenApart() {
        XCTAssertEqual(
            SentenceSplitter.split("I built “Innomight. Labs” last year. It grew."),
            ["I built “Innomight. Labs” last year.", "It grew."]
        )
    }

    func testClosingQuotesStayWithTheirSentence() {
        XCTAssertEqual(SentenceSplitter.split("He said \"go.\" Then he left."), ["He said \"go.\"", "Then he left."])
    }

    func testEmptyAndPunctuationOnlyInputGivesNothing() {
        XCTAssertEqual(SentenceSplitter.split(""), [])
        XCTAssertEqual(SentenceSplitter.split("   \n "), [])
        XCTAssertEqual(SentenceSplitter.split("... !!"), [])
    }

    func testAnOverlongSentenceIsSplitAtItsCommasKeepingEveryWord() {
        let clause = "this is a clause with a fair number of words in it"
        let sentence = Array(repeating: clause, count: 5).joined(separator: ", ") + "."
        XCTAssertGreaterThan(sentence.count, SentenceSplitter.maximumCharacters)

        let pieces = SentenceSplitter.split(sentence)

        XCTAssertGreaterThan(pieces.count, 1)
        XCTAssertTrue(pieces.allSatisfy { $0.count <= SentenceSplitter.maximumCharacters })
        XCTAssertEqual(pieces.joined(separator: " ").replacingOccurrences(of: ",", with: ""),
                       sentence.replacingOccurrences(of: ",", with: ""))
    }

    func testAnOverlongSentenceWithNoPunctuationIsSplitAtSpaces() {
        let sentence = Array(repeating: "word", count: 80).joined(separator: " ")
        let pieces = SentenceSplitter.split(sentence)

        XCTAssertTrue(pieces.allSatisfy { $0.count <= SentenceSplitter.maximumCharacters })
        XCTAssertEqual(pieces.joined(separator: " "), sentence)
    }
}
