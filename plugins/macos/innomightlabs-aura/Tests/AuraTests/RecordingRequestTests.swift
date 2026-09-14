import XCTest
@testable import Aura

final class RecordingRequestTests: XCTestCase {
    func testEmptyProfileIsInvalidRegardlessOfTarget() {
        let request = RecordingRequest(profile: RecordingProfile(tracks: []), screenTarget: nil)
        XCTAssertFalse(request.isValid)
    }

    func testScreenOnlyWithNoTargetIsInvalid() {
        let request = RecordingRequest(profile: RecordingProfile(tracks: [.screen]), screenTarget: nil)
        XCTAssertFalse(request.isValid)
    }

    func testSystemAudioOnlyWithNoTargetIsInvalid() {
        // System audio still needs an `SCContentFilter`, so it is subject to the same
        // requirement as a screen recording even though no video is captured.
        let request = RecordingRequest(profile: RecordingProfile(tracks: [.systemAudio]), screenTarget: nil)
        XCTAssertFalse(request.isValid)
    }

    func testCameraAndMicrophoneWithNoTargetIsValid() {
        let request = RecordingRequest(
            profile: RecordingProfile(tracks: [.camera, .microphone]),
            screenTarget: nil,
            cameraDeviceID: "cam-1",
            microphoneDeviceID: "mic-1"
        )
        XCTAssertTrue(request.isValid)
    }
}
