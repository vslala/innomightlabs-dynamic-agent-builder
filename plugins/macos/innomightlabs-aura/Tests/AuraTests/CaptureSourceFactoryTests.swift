import XCTest
@testable import Aura

/// `CaptureTarget` wraps `SCDisplay`/`SCWindow`/`SCRunningApplication`, none of which has a
/// public initializer — they only come from a live `SCShareableContent` lookup. So the cases
/// here are the ones the factory can be exercised on without one: profiles that need no
/// screen target at all, and the "screen was wanted but no target was supplied" case, which is
/// exactly the situation `RecordingRequest.isValid` already rejects. The "one source for both
/// screen and system audio" property is covered at the pure-model layer instead, by
/// `RecordingProfileTests.testScreenCaptureKindsCoversBothScreenAndSystemAudio` — that Set
/// intersection is what the factory below reads to decide whether to build a
/// `ScreenCaptureSource` at all.
final class CaptureSourceFactoryTests: XCTestCase {
    func testPodcastProfileProducesOneMicrophoneSource() {
        let request = RecordingRequest(profile: RecordingPreset.podcast.profile, screenTarget: nil)
        let sources = CaptureSourceFactory.sources(for: request)

        XCTAssertEqual(sources.count, 1)
        XCTAssertEqual(sources.flatMap(\.kinds), [.microphone])
        XCTAssertTrue(sources.first is MicrophoneCaptureSource)
    }

    func testCameraOnlyProfileProducesCameraAndMicrophoneSourcesButNoScreenSource() {
        let request = RecordingRequest(profile: RecordingPreset.cameraOnly.profile, screenTarget: nil)
        let sources = CaptureSourceFactory.sources(for: request)

        XCTAssertEqual(Set(sources.flatMap(\.kinds)), [.camera, .microphone])
        XCTAssertFalse(sources.contains { $0 is ScreenCaptureSource })
    }

    /// A profile that wants screen video but was given no target builds no screen source at
    /// all — matching `RecordingRequest.isValid == false` for the same case, rather than
    /// producing a source that would fail later.
    func testScreenRequestedWithNoTargetProducesNoScreenSource() {
        let request = RecordingRequest(
            profile: RecordingProfile(tracks: [.screen, .camera]),
            screenTarget: nil,
            cameraDeviceID: "cam-1"
        )
        let sources = CaptureSourceFactory.sources(for: request)

        XCTAssertFalse(sources.contains { $0 is ScreenCaptureSource })
        XCTAssertEqual(sources.flatMap(\.kinds), [.camera])
    }

    func testSystemAudioOnlyWithNoTargetProducesNoSources() {
        let request = RecordingRequest(profile: RecordingProfile(tracks: [.systemAudio]), screenTarget: nil)
        XCTAssertTrue(CaptureSourceFactory.sources(for: request).isEmpty)
    }

    func testEmptyProfileProducesNoSources() {
        let request = RecordingRequest(profile: RecordingProfile(tracks: []), screenTarget: nil)
        XCTAssertTrue(CaptureSourceFactory.sources(for: request).isEmpty)
    }
}
