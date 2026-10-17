import XCTest
@testable import Aura

final class VoiceReferencePickerTests: XCTestCase {
    /// Evenly spaced words at 3 words a second, so a run's duration is easy to reason about.
    private func speech(_ texts: [String], from start: TimeInterval = 0, pace: TimeInterval = 1.0 / 3) -> [Transcript.Word] {
        texts.enumerated().map { index, text in
            let wordStart = start + Double(index) * pace
            return Transcript.Word(id: index, start: wordStart, end: wordStart + pace * 0.9, text: text)
        }
    }

    private func sentence(words count: Int, endingWith mark: String = ".") -> [String] {
        (0..<count).map { "word\($0)" } .enumerated().map { $0.offset == count - 1 ? $0.element + mark : $0.element }
    }

    func testPicksARunBetweenSixAndTenSeconds() throws {
        let reference = try XCTUnwrap(VoiceReferencePicker.pick(words: speech(sentence(words: 60))))

        XCTAssertGreaterThanOrEqual(reference.duration, VoiceReferencePicker.minimumDuration)
        XCTAssertLessThanOrEqual(reference.duration, VoiceReferencePicker.maximumDuration)
    }

    func testPrefersToEndWhereASentenceEnds() throws {
        var texts = sentence(words: 60, endingWith: "")
        texts[24] += "."   // ends at about 8.3s: the ideal length
        let reference = try XCTUnwrap(VoiceReferencePicker.pick(words: speech(texts)))

        XCTAssertTrue(reference.text.hasSuffix("word24."), "ended mid-sentence: \(reference.text)")
    }

    func testNeverIncludesAFillerWord() throws {
        var texts = sentence(words: 80)
        texts[10] = "um"
        texts[40] = "Uh,"
        let words = speech(texts)
        let reference = try XCTUnwrap(VoiceReferencePicker.pick(words: words))

        XCTAssertFalse(reference.text.lowercased().contains("um"))
        XCTAssertFalse(reference.text.lowercased().contains("uh"))
        // The only fluent stretches are 11–39 and 41–79 words long, both over 6 seconds.
        XCTAssertGreaterThan(reference.start, words[10].start)
    }

    func testAPauseInsideTheClipDisqualifiesTheRunAcrossIt() throws {
        // Speech with a long pause every 5 seconds: no 6 second stretch is unbroken.
        var words: [Transcript.Word] = []
        for block in 0..<6 {
            words += speech(sentence(words: 14), from: Double(block) * 6.0).map {
                Transcript.Word(id: words.count + $0.id, start: $0.start, end: $0.end, text: $0.text)
            }
        }
        XCTAssertNil(VoiceReferencePicker.pick(words: words))
    }

    func testAvoidsStretchesThatAreOffLimits() throws {
        let words = speech(sentence(words: 90))        // 30 seconds
        let reference = try XCTUnwrap(VoiceReferencePicker.pick(words: words, avoiding: [TimeSpan(start: 0, end: 18)]))

        XCTAssertGreaterThanOrEqual(reference.start, 18)
    }

    func testTooFastOrTooSlowSpeechIsDistrusted() {
        // 8 words in 8 seconds is a pace no real sentence has; the timing is probably wrong.
        XCTAssertNil(VoiceReferencePicker.pick(words: speech(sentence(words: 8), pace: 1.0)))
    }

    func testNotEnoughSpeechGivesNothing() {
        XCTAssertNil(VoiceReferencePicker.pick(words: []))
        XCTAssertNil(VoiceReferencePicker.pick(words: speech(sentence(words: 12))))   // 4 seconds
    }

    func testTheTextIsTheWordsAsSpoken() throws {
        let words = speech(sentence(words: 40))
        let reference = try XCTUnwrap(VoiceReferencePicker.pick(words: words))

        let spoken = words.filter { $0.start >= reference.start && $0.end <= reference.end }.map(\.text)
        XCTAssertEqual(reference.text, spoken.joined(separator: " "))
    }
}
