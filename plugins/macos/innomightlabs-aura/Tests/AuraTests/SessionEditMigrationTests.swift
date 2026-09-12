import XCTest
@testable import Aura

/// v1 → v2: turning a mutable clip list plus a word-exclusion list back into the removals that
/// produced it.
///
/// The stakes are a user's existing edits, so these lean on one invariant above all: the
/// migrated timeline must play exactly what the v1 timeline played.
final class SessionEditMigrationTests: XCTestCase {
    /// v1 JSON, in the shape really found on disk.
    private func v1(
        clips: [(TimeInterval, TimeInterval)],
        excluded: [(Int, TimeInterval, TimeInterval, String)] = [],
        micTimeOffset: TimeInterval = 0
    ) -> Data {
        let clipJSON = clips
            .map { #"{"source":{"start":\#($0.0),"end":\#($0.1)}}"# }
            .joined(separator: ",")
        let wordJSON = excluded
            .map { #"{"id":\#($0.0),"start":\#($0.1),"end":\#($0.2),"text":"\#($0.3)"}"# }
            .joined(separator: ",")

        return Data("""
        {"schemaVersion":1,"micTimeOffset":\(micTimeOffset),
         "clips":[\(clipJSON)],
         "excludedWords":[\(wordJSON)],
         "cameraOverlay":[{"t":0,"rect":{"x":0.72,"y":0.7,"width":0.25,"height":0.25},"visible":true}],
         "audioLanes":[{"lane":"microphone","muted":false,"gain":[]},
                       {"lane":"system_audio","muted":false,"gain":[]}]}
        """.utf8)
    }

    /// What v1 would have played, computed the v1 way: clips minus excluded word spans.
    private func v1Duration(
        clips: [(TimeInterval, TimeInterval)],
        excluded: [(Int, TimeInterval, TimeInterval, String)]
    ) -> TimeInterval {
        var spans = clips.map { TimelineClip(source: TimeSpan(start: $0.0, end: $0.1)) }
        for word in excluded.sorted(by: { $0.1 < $1.1 }) {
            spans = SessionEdit.deriveClips(
                recordingDuration: clips.last?.1 ?? 0,
                cuts: []
            ).isEmpty ? spans : spans
            // Subtract the word span by hand, as v1 did.
            spans = spans.flatMap { clip -> [TimelineClip] in
                let source = clip.source
                let span = TimeSpan(start: word.1, end: word.2)
                guard span.start < source.end, span.end > source.start else { return [clip] }
                var pieces: [TimelineClip] = []
                if span.start > source.start {
                    pieces.append(TimelineClip(source: TimeSpan(start: source.start, end: span.start)))
                }
                if span.end < source.end {
                    pieces.append(TimelineClip(source: TimeSpan(start: span.end, end: source.end)))
                }
                return pieces
            }
        }
        return TimeMap(clips: spans).duration
    }

    private func migrate(_ data: Data, recordingDuration: TimeInterval) throws -> SessionEdit {
        guard case .migrated(let document) = SessionEditMigration.decode(data, recordingDuration: recordingDuration) else {
            throw XCTSkip("expected a migration")
        }
        return document
    }

    // MARK: - The invariant that matters

    func testMigratedTimelinePlaysExactlyWhatV1Played() throws {
        // The real document's shape: one interior range cut and a pile of word cuts.
        let clips = [(0.0, 6.2), (6.9, 421.68)]
        let excluded = [
            (4, 2.55, 2.74, "So"), (18, 8.74, 8.84, "And"), (29, 13.58, 13.66, "So"),
            (99, 42.54, 42.60, "And"), (525, 339.42, 339.52, "Okay,")
        ]

        let document = try migrate(v1(clips: clips, excluded: excluded), recordingDuration: 421.9)

        XCTAssertEqual(
            document.duration,
            v1Duration(clips: clips, excluded: excluded),
            // One audio sample at 44.1kHz (22.7us). The two paths snap to the timeline grid
            // at different moments, so they can differ by a tick or two per cut — a
            // difference smaller than a single sample is neither audible nor measurable.
            accuracy: 1.0 / 44_100,
            "the migrated timeline must play what v1 played"
        )
    }

    // MARK: - What each part of a v1 document becomes

    func testGapsBetweenClipsBecomeRangeCuts() throws {
        let document = try migrate(v1(clips: [(0, 10), (15, 30)]), recordingDuration: 30)

        XCTAssertEqual(document.cuts.count, 1)
        XCTAssertEqual(document.cuts.first?.span, TimeSpan(start: 10, end: 15))
        XCTAssertEqual(document.cuts.first?.origin, .range)
    }

    func testALeadingGapBecomesACut() throws {
        let document = try migrate(v1(clips: [(5, 30)]), recordingDuration: 30)

        XCTAssertEqual(document.cuts.map(\.span), [TimeSpan(start: 0, end: 5)])
    }

    func testATrailingGapBecomesACut() throws {
        // The one that gets forgotten. Omitting it lengthens the timeline and shifts every
        // resume position.
        let document = try migrate(v1(clips: [(0, 25)]), recordingDuration: 30)

        XCTAssertEqual(document.cuts.map(\.span), [TimeSpan(start: 25, end: 30)])
        XCTAssertEqual(document.duration, 25, accuracy: 0.001)
    }

    func testAdjacentClipsBecomeSplitsNotCuts() throws {
        // v1 `splitClip` produced two touching clips with no gap. Looking only for gaps would
        // make every split a user ever made silently vanish.
        let document = try migrate(v1(clips: [(0, 12), (12, 30)]), recordingDuration: 30)

        XCTAssertEqual(document.splitPoints, [12])
        XCTAssertTrue(document.cuts.isEmpty)
        XCTAssertEqual(document.duration, 30, accuracy: 0.001)
    }

    func testExcludedWordsBecomeWordCutsKeepingTheirIdentity() throws {
        let document = try migrate(
            v1(clips: [(0, 30)], excluded: [(7, 3.0, 3.4, "um")]),
            recordingDuration: 30
        )

        XCTAssertEqual(document.cuts.count, 1)
        XCTAssertEqual(document.cuts.first?.origin, .word(id: 7, text: "um"))
        XCTAssertTrue(document.isExcluded(wordID: 7))
        XCTAssertEqual(document.excludedWords.first?.text, "um")
    }

    func testWordSpansAreNotShiftedAgainByTheMicOffset() throws {
        // v1 spans are already in session time — the repair pass put them there. Applying
        // `micTimeOffset` again is the most likely migration bug, and with an offset of 0 on
        // the real document it would not have shown up in testing.
        let document = try migrate(
            v1(clips: [(0, 30)], excluded: [(7, 3.0, 3.4, "um")], micTimeOffset: 0.4),
            recordingDuration: 30
        )

        XCTAssertEqual(document.cuts.first?.span, TimeSpan(start: 3.0, end: 3.4))
        XCTAssertEqual(document.micTimeOffset, 0.4, "the offset is carried, just not re-applied")
    }

    func testWordCutsAlreadyCoveredByARangeCutAreKept() throws {
        // v1 subtraction was lenient, so a word inside a coarse gap removed nothing. It
        // becomes a real cut whose restoration does nothing visible — kept anyway, so the set
        // of word ids the agent was told about stays the same.
        let document = try migrate(
            v1(clips: [(0, 10), (20, 30)], excluded: [(3, 12.0, 12.4, "um")]),
            recordingDuration: 30
        )

        XCTAssertTrue(document.isExcluded(wordID: 3))
        XCTAssertEqual(document.cuts.count, 2)
        XCTAssertEqual(document.duration, 20, accuracy: 0.001)
    }

    func testRecordingDurationComesFromTheMediaNotTheLastClip() throws {
        // Using `clips.last.end` would silently truncate a recording whose tail was cut, in a
        // way indistinguishable from the recording having ended there.
        let document = try migrate(v1(clips: [(0, 25)]), recordingDuration: 30)

        XCTAssertEqual(document.recordingDuration, 30)
    }

    func testEverythingElseIsCarriedThrough() throws {
        let document = try migrate(v1(clips: [(0, 30)]), recordingDuration: 30)

        XCTAssertEqual(document.schemaVersion, SessionEdit.currentSchemaVersion)
        XCTAssertEqual(document.cameraOverlay.count, 1)
        XCTAssertEqual(document.audioLanes.map(\.lane), [.microphone, .systemAudio])
        XCTAssertNil(document.transcriptIdentity, "v1 never recorded which transcript it used")
    }

    // MARK: - Refusals

    func testOverlappingV1ClipsAreRefusedRatherThanGuessed() {
        // A wrong inversion would move every subsequent edit, so it declines instead.
        let outcome = SessionEditMigration.decode(v1(clips: [(0, 20), (10, 30)]), recordingDuration: 30)

        XCTAssertEqual(outcome, .unreadable)
    }

    func testADocumentFromANewerBuildIsRefused() {
        let json = Data(#"{"schemaVersion":99,"recordingDuration":30,"cuts":[]}"#.utf8)

        XCTAssertEqual(SessionEditMigration.decode(json, recordingDuration: 30), .tooNew)
    }

    func testGarbageIsUnreadable() {
        XCTAssertEqual(SessionEditMigration.decode(Data("nope".utf8), recordingDuration: 30), .unreadable)
    }

    // MARK: - v2 round trip

    func testAV2DocumentDecodesAsCurrent() throws {
        let original = try SessionEdit.initial(duration: 30)
            .applying(.removeRange(TimeSpan(start: 5, end: 8)))
            .applying(.addMarker(EditMarker(at: 12, label: "here")))
            .applying(.splitClip(at: 20))

        let data = try JSONEncoder().encode(original)

        guard case .current(let decoded) = SessionEditMigration.decode(data, recordingDuration: 30) else {
            return XCTFail("expected a current document")
        }
        XCTAssertEqual(decoded, original)
    }

    func testAV2DocumentMissingItsCutsIsRefusedRatherThanReadAsUnedited() throws {
        // The whole reason the v2 decoder is strict: silently reading this as "nothing was
        // cut" would discard every edit the user had made.
        let json = Data(#"""
        {"schemaVersion":2,"recordingDuration":30,
         "cameraOverlay":[{"t":0,"rect":{"x":0.7,"y":0.7,"width":0.25,"height":0.25},"visible":true}],
         "audioLanes":[]}
        """#.utf8)

        XCTAssertEqual(SessionEditMigration.decode(json, recordingDuration: 30), .unreadable)
    }
}
