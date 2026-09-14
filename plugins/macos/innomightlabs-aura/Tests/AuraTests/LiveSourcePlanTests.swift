import XCTest
@testable import Aura

/// A minimal stand-in for a device-backed `CaptureSource`, identified only by the kinds it
/// owns — everything `LiveSourcePlan.reconciling` looks at. Real sources like
/// `ScreenCaptureSource` wrap `SCDisplay`/`SCWindow`, which have no public initializer outside
/// a live device lookup, so a fake is what lets the screen+system-audio identity behaviour be
/// tested at all.
private final class FakeCaptureSource: CaptureSource, @unchecked Sendable {
    let kinds: [TrackKind]
    var writers: [TrackKind: TrackWriter] = [:]
    var onFailure: (@Sendable (Error) -> Void)?

    init(_ kinds: TrackKind...) { self.kinds = kinds }

    func prepare() async throws {}
    func start(context: CaptureContext) async throws {}
    func stop() async {}
    func cancel() {}
}

final class LiveSourcePlanTests: XCTestCase {
    private func reconcile(live: [any CaptureSource], desired: [any CaptureSource]) -> LiveSourcePlan {
        .reconciling(live: live, desired: desired)
    }

    func testUnchangedSourcesPlanEmpty() {
        let camera = FakeCaptureSource(.camera)
        let mic = FakeCaptureSource(.microphone)

        let plan = reconcile(live: [camera, mic], desired: [camera, mic])

        XCTAssertTrue(plan.isEmpty)
        XCTAssertEqual(Set(plan.retained.flatMap(\.kinds)), [.camera, .microphone])
    }

    /// The feature's motivating case: adding a screen+system-audio source must retain — not
    /// restart — camera and microphone sources that are unrelated to the change.
    func testAddingAStreamSourceRetainsUnrelatedSources() {
        let camera = FakeCaptureSource(.camera)
        let mic = FakeCaptureSource(.microphone)
        let stream = FakeCaptureSource(.screen, .systemAudio)

        let plan = reconcile(live: [camera, mic], desired: [camera, mic, stream])

        XCTAssertEqual(Set(plan.retained.flatMap(\.kinds)), [.camera, .microphone])
        XCTAssertEqual(plan.added.flatMap(\.kinds), [.screen, .systemAudio])
        XCTAssertTrue(plan.removed.isEmpty)
    }

    /// The round trip a user doing A→B→A performs: removing exactly what was added, retaining
    /// exactly what was never touched.
    func testRemovingAStreamSourceRetainsUnrelatedSources() {
        let camera = FakeCaptureSource(.camera)
        let mic = FakeCaptureSource(.microphone)
        let stream = FakeCaptureSource(.screen, .systemAudio)

        let plan = reconcile(live: [camera, mic, stream], desired: [camera, mic])

        XCTAssertEqual(Set(plan.retained.flatMap(\.kinds)), [.camera, .microphone])
        XCTAssertEqual(plan.removed.flatMap(\.kinds), [.screen, .systemAudio])
        XCTAssertTrue(plan.added.isEmpty)
    }

    /// One `SCStream`-backed source owns both `.screen` and `.systemAudio`. Its identity is
    /// the *set* it owns, so narrowing that set to just one of the two rebuilds the source
    /// rather than "retaining" a source whose kind set no longer matches what is wanted.
    func testNarrowingAStreamSourcesKindsRebuildsRatherThanRetains() {
        let both = FakeCaptureSource(.screen, .systemAudio)
        let screenOnly = FakeCaptureSource(.screen)

        let plan = reconcile(live: [both], desired: [screenOnly])

        XCTAssertEqual(plan.removed.flatMap(\.kinds), [.screen, .systemAudio])
        XCTAssertEqual(plan.added.flatMap(\.kinds), [.screen])
        XCTAssertTrue(plan.retained.isEmpty)
    }

    func testResultingIsRetainedPlusAdded() {
        let camera = FakeCaptureSource(.camera)
        let mic = FakeCaptureSource(.microphone)

        let plan = reconcile(live: [camera], desired: [camera, mic])

        XCTAssertEqual(Set(plan.resulting.flatMap(\.kinds)), [.camera, .microphone])
        XCTAssertEqual(plan.resulting.count, plan.retained.count + plan.added.count)
    }

    // MARK: - CaptureSourceFactory.plan wiring

    /// End-to-end through the real factory, for a case that needs no screen target — matching
    /// the constraint documented on `CaptureSourceFactoryTests`.
    func testFactoryPlanRetainsCameraAcrossAMicrophoneOnlyChange() {
        let live = CaptureSourceFactory.sources(
            for: RecordingRequest(profile: RecordingProfile(tracks: [.camera]), screenTarget: nil)
        )
        let plan = CaptureSourceFactory.plan(
            live: live,
            for: RecordingRequest(profile: RecordingProfile(tracks: [.camera, .microphone]), screenTarget: nil)
        )

        XCTAssertEqual(Set(plan.retained.flatMap(\.kinds)), [.camera])
        XCTAssertEqual(plan.added.flatMap(\.kinds), [.microphone])
        XCTAssertTrue(plan.removed.isEmpty)
    }
}
