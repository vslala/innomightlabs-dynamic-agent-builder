import XCTest
import AVFoundation
import CoreMedia
@testable import Aura

final class TimelineResolverTests: XCTestCase {
    private func probe(
        _ kind: TrackKind,
        seconds: TimeInterval = 30,
        displaySize: CGSize? = CGSize(width: 1920, height: 1080)
    ) -> SourceTrackProbe {
        SourceTrackProbe(
            url: URL(fileURLWithPath: "/tmp/aura-tests/\(kind.rawValue)"),
            kind: kind,
            duration: Timeline.time(seconds: seconds),
            displaySize: kind.isVideo ? displaySize : nil,
            preferredTransform: .identity
        )
    }

    private var allProbes: [SourceTrackProbe] {
        [probe(.screen), probe(.camera, displaySize: CGSize(width: 1280, height: 720)),
         probe(.microphone), probe(.systemAudio)]
    }

    // MARK: - Invariants that keep uncatchable exceptions out of AVFoundation

    func testRenderSizeAndFrameDurationAreAlwaysPositive() {
        // A zero renderSize or frameDuration raises an uncatchable ObjC exception when the
        // composition reaches an AVPlayerItem, so there must be no input that produces one.
        let cases: [[SourceTrackProbe]] = [
            allProbes,
            [],
            [probe(.microphone)],
            [probe(.screen, displaySize: CGSize(width: 1, height: 1))]
        ]

        for probes in cases {
            let resolved = TimelineResolver.resolve(document: .initial(duration: 30), probes: probes)
            XCTAssertGreaterThan(resolved.renderSize.width, 0)
            XCTAssertGreaterThan(resolved.renderSize.height, 0)
            XCTAssertGreaterThan(resolved.frameDuration, .zero)
        }
    }

    func testRenderSizeIsEvenInBothDimensions() {
        let resolved = TimelineResolver.resolve(
            document: .initial(duration: 30),
            probes: [probe(.screen, displaySize: CGSize(width: 3023, height: 1963))]
        )

        XCTAssertEqual(resolved.renderSize, CGSize(width: 3022, height: 1962))
    }

    func testRenderSizeComesFromTheBaseTrackNotTheOverlay() {
        let resolved = TimelineResolver.resolve(document: .initial(duration: 30), probes: allProbes)
        XCTAssertEqual(resolved.renderSize, CGSize(width: 1920, height: 1080))
    }

    func testEveryKeyframeListIsNonEmptyAndStartsAtZero() {
        let resolved = TimelineResolver.resolve(document: .initial(duration: 30), probes: allProbes)

        // Leaving a layer without an explicit transform and opacity at the instruction start
        // makes AVFoundation hold it at the identity transform — the camera would render
        // full-size in the top-left corner, covering the screen.
        XCTAssertEqual(resolved.base?.keyframes.first?.at, .zero)
        XCTAssertEqual(resolved.overlay?.keyframes.first?.at, .zero)
        XCTAssertFalse(resolved.overlay?.keyframes.isEmpty ?? true)
        for lane in resolved.audio {
            XCTAssertEqual(lane.keyframes.first?.at, .zero)
        }
    }

    func testKeyframesAreSortedAndNumeric() throws {
        let edit = try SessionEdit.initial(duration: 60)
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 40, rect: .defaultCameraOverlay, visible: false)))
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 20, rect: NormalizedRect(x: 0.1, y: 0.1, width: 0.2, height: 0.2), visible: true)))

        let keyframes = try XCTUnwrap(
            TimelineResolver.resolve(document: edit, probes: allProbes).overlay?.keyframes
        )

        XCTAssertEqual(keyframes.map(\.at), keyframes.map(\.at).sorted())
        XCTAssertTrue(keyframes.allSatisfy { $0.at.isNumeric })
    }

    func testEmptyDocumentStillResolvesOneOverlayKeyframe() {
        var edit = SessionEdit.initial(duration: 30)
        edit.cameraOverlay = []
        // An empty timeline is now expressed the only way it can be: everything cut.
        edit.cuts = [Cut(span: TimeSpan(start: 0, end: 30), origin: .range)]

        let resolved = TimelineResolver.resolve(document: edit, probes: allProbes)

        XCTAssertEqual(resolved.overlay?.keyframes.count, 1)
        XCTAssertEqual(resolved.overlay?.keyframes.first?.at, .zero)
    }

    // MARK: - Layer identity

    func testScreenIsTheBaseLayerAndCameraTheOverlay() {
        let resolved = TimelineResolver.resolve(document: .initial(duration: 30), probes: allProbes)

        XCTAssertEqual(resolved.base?.probe.kind, .screen)
        XCTAssertEqual(resolved.overlay?.probe.kind, .camera)
    }

    func testCameraIsPromotedToFullFrameWhenTheScreenTrackIsUnusable() {
        // Recording a static screen can produce a screen.mov with no frames at all, since
        // only complete frames are forwarded and there is no maximum frame interval.
        let resolved = TimelineResolver.resolve(
            document: .initial(duration: 30),
            probes: [probe(.camera, displaySize: CGSize(width: 1280, height: 720)), probe(.microphone)]
        )

        XCTAssertEqual(resolved.base?.probe.kind, .camera)
        XCTAssertNil(resolved.overlay, "Promoting the camera must not also leave it as a PiP")
        XCTAssertEqual(resolved.renderSize, CGSize(width: 1280, height: 720))
    }

    func testNoVideoAtAllResolvesWithoutABaseLayer() {
        let resolved = TimelineResolver.resolve(
            document: .initial(duration: 30),
            probes: [probe(.microphone), probe(.systemAudio)]
        )

        XCTAssertNil(resolved.base)
        XCTAssertFalse(resolved.hasVideo)
        XCTAssertEqual(resolved.audio.count, 2)
        XCTAssertEqual(resolved.renderSize, TimelineResolver.fallbackRenderSize)
    }

    func testMissingCameraLeavesNoOverlayLayer() {
        let resolved = TimelineResolver.resolve(
            document: .initial(duration: 30),
            probes: [probe(.screen), probe(.microphone)]
        )

        XCTAssertEqual(resolved.base?.probe.kind, .screen)
        XCTAssertNil(resolved.overlay)
    }

    func testOnlyLanesWithARecordedFileAreResolved() {
        let resolved = TimelineResolver.resolve(
            document: .initial(duration: 30),
            probes: [probe(.screen), probe(.microphone)]
        )

        XCTAssertEqual(resolved.audio.map(\.lane), [.microphone])
    }

    // MARK: - Projecting source keyframes onto the composition timeline

    func testOverlayKeyframeMovesEarlierWhenAnEarlierRangeIsCut() throws {
        let hidden = NormalizedRect(x: 0.5, y: 0.5, width: 0.2, height: 0.2)
        let edit = try SessionEdit.initial(duration: 30)
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 20, rect: hidden, visible: false)))
            .applying(.removeRange(TimeSpan(start: 5, end: 10)))

        let keyframes = try XCTUnwrap(
            TimelineResolver.resolve(document: edit, probes: allProbes).overlay?.keyframes
        )

        XCTAssertEqual(keyframes.map { Timeline.seconds($0.at) }, [0, 15])
        XCTAssertEqual(keyframes.last?.visible, false)
    }

    func testKeyframeInsideACutRangeStillGovernsTheContentAfterIt() throws {
        // The case that is easy to get wrong: the keyframe at 7 maps to no composition time
        // of its own once 5-10 is removed, but the state it set must still apply to
        // everything after it rather than being silently dropped.
        let hidden = NormalizedRect(x: 0.5, y: 0.5, width: 0.2, height: 0.2)
        let edit = try SessionEdit.initial(duration: 30)
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 7, rect: hidden, visible: false)))
            .applying(.removeRange(TimeSpan(start: 5, end: 10)))

        let keyframes = try XCTUnwrap(
            TimelineResolver.resolve(document: edit, probes: allProbes).overlay?.keyframes
        )

        XCTAssertEqual(keyframes.map { Timeline.seconds($0.at) }, [0, 5])
        XCTAssertEqual(keyframes.first?.visible, true)
        XCTAssertEqual(keyframes.last?.visible, false, "The hidden state set at 7 must survive the cut")
    }

    func testRedundantKeyframesAreCollapsed() throws {
        // Re-stating the same rect and visibility should not add instructions.
        let edit = try SessionEdit.initial(duration: 30)
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 10, rect: .defaultCameraOverlay, visible: true)))
            .applying(.setOverlayKeyframe(OverlayKeyframe(t: 20, rect: .defaultCameraOverlay, visible: true)))

        let keyframes = try XCTUnwrap(
            TimelineResolver.resolve(document: edit, probes: allProbes).overlay?.keyframes
        )

        XCTAssertEqual(keyframes.count, 1)
    }

    func testGainKeyframesProjectOntoTheCompositionTimeline() throws {
        let edit = try SessionEdit.initial(duration: 30)
            .applying(.setLaneGain(lane: .systemAudio, keyframe: GainKeyframe(t: 20, gain: 0.25)))
            .applying(.removeRange(TimeSpan(start: 5, end: 10)))

        let lane = try XCTUnwrap(
            TimelineResolver.resolve(document: edit, probes: allProbes).audio.first { $0.lane == .systemAudio }
        )

        XCTAssertEqual(lane.keyframes.map { Timeline.seconds($0.at) }, [0, 15])
        XCTAssertEqual(lane.keyframes.last?.gain, 0.25)
    }

    func testMutedLaneResolvesToZeroGain() throws {
        let edit = try SessionEdit.initial(duration: 30)
            .applying(.setLaneMuted(lane: .microphone, muted: true))

        let lane = try XCTUnwrap(
            TimelineResolver.resolve(document: edit, probes: allProbes).audio.first { $0.lane == .microphone }
        )

        XCTAssertEqual(lane.keyframes.map(\.gain), [0])
    }

    func testLanesResolveIndependently() throws {
        let edit = try SessionEdit.initial(duration: 30)
            .applying(.setLaneMuted(lane: .systemAudio, muted: true))

        let resolved = TimelineResolver.resolve(document: edit, probes: allProbes)
        let mic = try XCTUnwrap(resolved.audio.first { $0.lane == .microphone })
        let system = try XCTUnwrap(resolved.audio.first { $0.lane == .systemAudio })

        XCTAssertEqual(mic.keyframes.map(\.gain), [1])
        XCTAssertEqual(system.keyframes.map(\.gain), [0])
    }

    func testDurationFollowsTheEditRatherThanTheSourceFiles() throws {
        let edit = try SessionEdit.initial(duration: 30)
            .applying(.removeRange(TimeSpan(start: 10, end: 20)))

        let resolved = TimelineResolver.resolve(document: edit, probes: allProbes)

        XCTAssertEqual(Timeline.seconds(resolved.duration), 20)
    }

    // MARK: - Display geometry

    func testDisplaySizeAppliesPreferredTransformWithoutNegativeDimensions() {
        let rotated = CGAffineTransform(rotationAngle: .pi / 2)
        let size = SourceTrackProbe.displaySize(
            naturalSize: CGSize(width: 1920, height: 1080),
            preferredTransform: rotated
        )

        XCTAssertEqual(size.width, 1080, accuracy: 0.001)
        XCTAssertEqual(size.height, 1920, accuracy: 0.001)
    }

    func testDisplaySizeOfAMirroredTrackStaysPositive() {
        let mirrored = CGAffineTransform(scaleX: -1, y: 1)
        let size = SourceTrackProbe.displaySize(
            naturalSize: CGSize(width: 1280, height: 720),
            preferredTransform: mirrored
        )

        XCTAssertEqual(size, CGSize(width: 1280, height: 720))
    }
}
