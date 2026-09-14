import XCTest
@testable import Aura

final class RecordingProfileTests: XCTestCase {
    func testPresetsRoundTripThroughMatching() {
        for preset in RecordingPreset.allCases {
            XCTAssertEqual(RecordingPreset.matching(preset.profile), preset, "\(preset) did not round-trip")
        }
    }

    func testCustomProfileMatchesNoPreset() {
        let custom = RecordingProfile(tracks: [.screen, .camera, .systemAudio])
        XCTAssertNil(RecordingPreset.matching(custom))
    }

    func testIsRecordableIsFalseOnlyForTheEmptySet() {
        XCTAssertFalse(RecordingProfile(tracks: []).isRecordable)
        for kind in TrackKind.allCases {
            XCTAssertTrue(RecordingProfile(tracks: [kind]).isRecordable)
        }
    }

    func testNeedsScreenCaptureStream() {
        XCTAssertTrue(RecordingProfile(tracks: [.screen]).needsScreenCaptureStream)
        XCTAssertTrue(RecordingProfile(tracks: [.systemAudio]).needsScreenCaptureStream)
        XCTAssertTrue(RecordingProfile(tracks: [.screen, .systemAudio]).needsScreenCaptureStream)
        XCTAssertFalse(RecordingProfile(tracks: [.camera, .microphone]).needsScreenCaptureStream)
        XCTAssertFalse(RecordingProfile(tracks: []).needsScreenCaptureStream)
    }

    /// The property that lets `CaptureSourceFactory` build exactly one `ScreenCaptureSource`
    /// for both screen and system audio: their union stays within `screenCaptureKinds`.
    func testScreenCaptureKindsCoversBothScreenAndSystemAudio() {
        let profile = RecordingProfile(tracks: [.screen, .systemAudio, .camera, .microphone])
        XCTAssertEqual(profile.screenCaptureKinds, [.screen, .systemAudio])
    }

    func testHasVideoAndIsAudioOnly() {
        XCTAssertTrue(RecordingProfile(tracks: [.screen]).hasVideo)
        XCTAssertTrue(RecordingProfile(tracks: [.camera]).hasVideo)
        XCTAssertFalse(RecordingProfile(tracks: [.microphone]).hasVideo)

        XCTAssertTrue(RecordingProfile(tracks: [.microphone]).isAudioOnly)
        XCTAssertTrue(RecordingProfile(tracks: [.microphone, .systemAudio]).isAudioOnly)
        XCTAssertFalse(RecordingProfile(tracks: [.screen, .microphone]).isAudioOnly)
        XCTAssertFalse(RecordingProfile(tracks: []).isAudioOnly)
    }

    func testEnabledKindsIsAlwaysInAllCasesOrderRegardlessOfInsertionOrder() {
        let profile = RecordingProfile(tracks: [.systemAudio, .screen, .microphone, .camera])
        XCTAssertEqual(profile.enabledKinds, TrackKind.allCases)
    }


    func testEventLabelIsOrderedAndJoined() {
        let profile = RecordingProfile(tracks: [.microphone, .screen])
        XCTAssertEqual(profile.eventLabel, "screen+microphone")
    }

    func testPodcastPresetIsMicrophoneOnly() {
        // Deliberately excludes system audio: it would drag in the Screen Recording
        // permission an audio-only recording otherwise never needs.
        XCTAssertEqual(RecordingPreset.podcast.profile.tracks, [.microphone])
    }

    func testCameraOnlyPresetIncludesTheMicrophone() {
        XCTAssertEqual(RecordingPreset.cameraOnly.profile.tracks, [.camera, .microphone])
    }

    func testFullStudioPresetIsEveryTrack() {
        XCTAssertEqual(RecordingPreset.fullStudio.profile.tracks, Set(TrackKind.allCases))
    }

    func testCameraQualityIsOverlayWithScreenAndPrimaryWithout() {
        XCTAssertEqual(CameraQuality(profile: RecordingProfile(tracks: [.screen, .camera])), .overlay)
        XCTAssertEqual(CameraQuality(profile: RecordingProfile(tracks: [.camera, .microphone])), .primary)
    }
}
