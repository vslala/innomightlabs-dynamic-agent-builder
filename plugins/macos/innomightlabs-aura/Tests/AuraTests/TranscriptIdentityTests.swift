import XCTest
@testable import Aura

/// Covers the fingerprint that decides whether a saved edit's word ids still mean what they
/// meant when it was authored.
final class TranscriptIdentityTests: XCTestCase {
    private func transcript(
        engine: String = "whisperkit/openai_whisper-base",
        words: [(Int, TimeInterval, TimeInterval, String)]
    ) -> Transcript {
        let mapped = words.map { Transcript.Word(id: $0.0, start: $0.1, end: $0.2, text: $0.3) }
        return Transcript(
            source: "microphone.m4a",
            engine: engine,
            segments: [Transcript.Segment(
                id: 0,
                start: mapped.first?.start ?? 0,
                end: mapped.last?.end ?? 0,
                text: mapped.map(\.text).joined(separator: " "),
                words: mapped
            )]
        )
    }

    private let sample: [(Int, TimeInterval, TimeInterval, String)] = [
        (0, 0.0, 0.4, "hello"),
        (1, 0.5, 0.9, "there"),
        (2, 1.0, 1.4, "everyone"),
    ]

    func testIdentityIsStableForTheSameContent() {
        XCTAssertEqual(transcript(words: sample).identity, transcript(words: sample).identity)
    }

    /// The property that makes it safe to persist. Swift seeds `Hasher` per process, so a
    /// `hashValue`-based identity would differ on every launch and detach every word cut from
    /// a transcript that had not changed.
    func testIdentityIsNotDerivedFromSwiftsPerProcessHasher() {
        var hasher = Hasher()
        hasher.combine("hello")
        let perProcess = String(hasher.finalize(), radix: 16)
        XCTAssertFalse(
            transcript(words: sample).identity.contains(perProcess),
            "identity must not embed a per-process hash — it is persisted in edit.json"
        )
    }

    func testIdentitySurvivesAJSONRoundTrip() throws {
        let original = transcript(words: sample)
        let decoded = try JSONDecoder().decode(Transcript.self, from: JSONEncoder().encode(original))
        XCTAssertEqual(original.identity, decoded.identity)
    }

    func testSubMillisecondTimingNoiseDoesNotChangeIdentity() {
        // A re-serialised transcript can differ in the last float digit without being a
        // different transcript.
        let jittered = sample.map { ($0.0, $0.1 + 0.00004, $0.2 - 0.00004, $0.3) }
        XCTAssertEqual(transcript(words: sample).identity, transcript(words: jittered).identity)
    }

    // MARK: - What must invalidate

    func testRenumberedWordsChangeIdentity() {
        let renumbered = sample.map { ($0.0 + 1, $0.1, $0.2, $0.3) }
        XCTAssertNotEqual(transcript(words: sample).identity, transcript(words: renumbered).identity)
    }

    func testDifferentTextAtTheSameIdChangesIdentity() {
        var changed = sample
        changed[1] = (1, 0.5, 0.9, "their")
        XCTAssertNotEqual(transcript(words: sample).identity, transcript(words: changed).identity)
    }

    func testRealTimingChangeAtTheSameIdChangesIdentity() {
        var changed = sample
        changed[1] = (1, 0.6, 1.0, "there")
        XCTAssertNotEqual(transcript(words: sample).identity, transcript(words: changed).identity)
    }

    func testDifferentWordCountChangesIdentity() {
        XCTAssertNotEqual(
            transcript(words: sample).identity,
            transcript(words: Array(sample.dropLast())).identity
        )
    }

    func testDifferentEngineChangesIdentity() {
        // A larger model resegments, so ids from `base` do not transfer to `large`.
        XCTAssertNotEqual(
            transcript(words: sample).identity,
            transcript(engine: "whisperkit/openai_whisper-large-v3", words: sample).identity
        )
    }

    func testWordCountIsLegibleInTheIdentity() {
        XCTAssertTrue(transcript(words: sample).identity.hasPrefix("w3-"))
    }
}
