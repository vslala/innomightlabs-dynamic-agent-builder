import XCTest
import AVFoundation
import CoreMedia
@testable import Aura

/// The A/V sync chain: what the recorder logged, what the file's edit list already accounts
/// for, and what therefore has to be corrected at playback.
final class TrackAlignmentTests: XCTestCase {
    private func probe(
        _ kind: TrackKind,
        recordedStartOffset: TimeInterval,
        leadingEmptyEdit: TimeInterval
    ) -> SourceTrackProbe {
        SourceTrackProbe(
            url: URL(fileURLWithPath: "/tmp/aura-tests/\(kind.rawValue)"),
            kind: kind,
            duration: Timeline.time(seconds: 30),
            displaySize: kind.isVideo ? CGSize(width: 1920, height: 1080) : nil,
            preferredTransform: .identity,
            leadingEmptyEdit: Timeline.time(seconds: leadingEmptyEdit),
            recordedStartOffset: Timeline.time(seconds: recordedStartOffset)
        )
    }

    // MARK: - The correction itself

    func testVideoNeedsNoCorrectionBecauseItsOffsetIsAlreadyAnEmptyEdit() {
        // AVAssetWriter preserves a video track's warm-up as a leading empty edit, so the
        // recorded offset and the file already agree.
        let screen = probe(.screen, recordedStartOffset: 0.13, leadingEmptyEdit: 0.13)

        XCTAssertEqual(Timeline.seconds(screen.alignmentCorrection), 0, accuracy: 0.0001)
    }

    func testAudioIsCorrectedByItsWholeRecordedOffset() {
        // For audio the writer slides the first sample to zero and discards the offset, which
        // is the desync: the audio plays early by its entire startup delay.
        let mic = probe(.microphone, recordedStartOffset: 0.35, leadingEmptyEdit: 0)

        XCTAssertEqual(Timeline.seconds(mic.alignmentCorrection), 0.35, accuracy: 0.0001)
    }

    func testCorrectionIsNeverNegative() {
        // A file whose empty edit exceeds what was recorded would otherwise pull content
        // earlier, which is never right.
        let odd = probe(.camera, recordedStartOffset: 0.1, leadingEmptyEdit: 1.0)

        XCTAssertEqual(odd.alignmentCorrection, .zero)
    }

    func testSessionsRecordedBeforeOffsetsWereLoggedGetNoAutomaticCorrection() {
        let legacy = probe(.microphone, recordedStartOffset: 0, leadingEmptyEdit: 0)

        XCTAssertEqual(legacy.alignmentCorrection, .zero)
    }

    // MARK: - Reading the offsets back out of the event log

    func testTrackStartOffsetsAreRecoveredFromTheEventLog() {
        let timeline = EventTimeline(events: [
            RecordingEvent(ts: 0, type: .recordStart, mediaTs: 0),
            RecordingEvent(ts: 0.13, type: .trackStart, mediaTs: 0.13, label: "screen"),
            RecordingEvent(ts: 1.02, type: .trackStart, mediaTs: 1.02, label: "camera"),
            RecordingEvent(ts: 0.35, type: .trackStart, mediaTs: 0.35, label: "microphone")
        ])

        XCTAssertEqual(timeline.trackStartOffsets["screen"] ?? -1, 0.13, accuracy: 0.0001)
        XCTAssertEqual(timeline.trackStartOffsets["camera"] ?? -1, 1.02, accuracy: 0.0001)
        XCTAssertEqual(timeline.trackStartOffsets["microphone"] ?? -1, 0.35, accuracy: 0.0001)
        XCTAssertNil(timeline.trackStartOffsets["system_audio"])
    }

    func testTrackStartEventsAreNotTreatedAsMarkers() {
        let timeline = EventTimeline(events: [
            RecordingEvent(ts: 0.35, type: .trackStart, mediaTs: 0.35, label: "microphone")
        ])

        XCTAssertTrue(timeline.markers.isEmpty)
    }

    // MARK: - What reaches the composition

    func testResolvedAudioLaneCarriesTheAutomaticCorrection() {
        let probes = [
            probe(.screen, recordedStartOffset: 0.13, leadingEmptyEdit: 0.13),
            probe(.microphone, recordedStartOffset: 0.35, leadingEmptyEdit: 0)
        ]

        let resolved = TimelineResolver.resolve(document: .initial(duration: 30), probes: probes)
        let mic = resolved.audio.first { $0.lane == .microphone }

        XCTAssertEqual(Timeline.seconds(mic?.timeOffset ?? .zero), 0.35, accuracy: 0.0001)
        XCTAssertEqual(resolved.base?.timeOffset, .zero)
    }

    func testManualSlipAddsToTheAutomaticCorrection() throws {
        let probes = [
            probe(.screen, recordedStartOffset: 0.13, leadingEmptyEdit: 0.13),
            probe(.microphone, recordedStartOffset: 0.35, leadingEmptyEdit: 0)
        ]
        let document = try SessionEdit.initial(duration: 30)
            .applying(.setLaneOffset(lane: .microphone, seconds: 0.05))

        let resolved = TimelineResolver.resolve(document: document, probes: probes)
        let mic = resolved.audio.first { $0.lane == .microphone }

        XCTAssertEqual(Timeline.seconds(mic?.timeOffset ?? .zero), 0.40, accuracy: 0.0001)
    }

    func testManualSlipCanPullALaneEarlier() throws {
        let probes = [probe(.microphone, recordedStartOffset: 0.35, leadingEmptyEdit: 0)]
        let document = try SessionEdit.initial(duration: 30)
            .applying(.setLaneOffset(lane: .microphone, seconds: -0.35))

        let resolved = TimelineResolver.resolve(document: document, probes: probes)

        XCTAssertEqual(Timeline.seconds(resolved.audio.first?.timeOffset ?? .zero), 0, accuracy: 0.0001)
    }

    func testLanesSlipIndependently() throws {
        let probes = [probe(.microphone, recordedStartOffset: 0, leadingEmptyEdit: 0),
                      probe(.systemAudio, recordedStartOffset: 0, leadingEmptyEdit: 0)]
        let document = try SessionEdit.initial(duration: 30)
            .applying(.setLaneOffset(lane: .microphone, seconds: 0.3))

        let resolved = TimelineResolver.resolve(document: document, probes: probes)

        XCTAssertEqual(Timeline.seconds(resolved.audio.first { $0.lane == .microphone }?.timeOffset ?? .zero), 0.3, accuracy: 0.0001)
        XCTAssertEqual(resolved.audio.first { $0.lane == .systemAudio }?.timeOffset, .zero)
    }

    // MARK: - The operation

    func testSlipRoundTripsThroughJSON() throws {
        let operation = EditOperation.setLaneOffset(lane: .microphone, seconds: -0.35)
        let data = try JSONEncoder().encode(operation)

        XCTAssertEqual(try JSONDecoder().decode(EditOperation.self, from: data), operation)

        let json = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(json["op"] as? String, "set_lane_offset")
        XCTAssertEqual(json["seconds"] as? Double, -0.35)
    }

    func testAbsurdSlipIsRejected() {
        XCTAssertThrowsError(
            try SessionEdit.initial(duration: 30).applying(.setLaneOffset(lane: .microphone, seconds: 30))
        ) { error in
            XCTAssertEqual(error as? EditOperationError, .offsetOutOfRange(30))
        }
    }

    func testSlipSurvivesTheDocumentRoundTrip() throws {
        let document = try SessionEdit.initial(duration: 30)
            .applying(.setLaneOffset(lane: .systemAudio, seconds: 0.25))

        let data = try JSONEncoder().encode(document)
        let decoded = try JSONDecoder().decode(SessionEdit.self, from: data)

        XCTAssertEqual(decoded.offset(for: .systemAudio), 0.25)
    }

    func testDocumentsWrittenBeforeSlipExistedStillLoad() throws {
        let json = """
        {"schemaVersion":1,"micTimeOffset":0,
         "clips":[{"source":{"start":0,"end":30}}],
         "cameraOverlay":[{"t":0,"rect":{"x":0.7,"y":0.7,"width":0.25,"height":0.25},"visible":true}],
         "audioLanes":[{"lane":"microphone","muted":false,"gain":[]}]}
        """
        guard case .migrated(let decoded) = SessionEditMigration.decode(Data(json.utf8), recordingDuration: 30) else {
            return XCTFail("expected a migration")
        }

        XCTAssertEqual(decoded.offset(for: .microphone), 0)
    }
}
