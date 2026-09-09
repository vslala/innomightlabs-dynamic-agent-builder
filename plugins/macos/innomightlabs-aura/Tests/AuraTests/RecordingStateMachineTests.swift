import XCTest
@testable import Aura

final class RecordingStateMachineTests: XCTestCase {
    func testFullLifecycleSucceeds() {
        var state = RecordingState.idle
        let path: [(RecordingEventTrigger, RecordingState)] = [
            (.start, .starting),
            (.didStart, .recording),
            (.pause, .paused),
            (.resume, .recording),
            (.stop, .stopping),
            (.didStop, .idle)
        ]
        for (trigger, expected) in path {
            switch RecordingStateMachine.transition(current: state, trigger: trigger) {
            case .success(let newState):
                XCTAssertEqual(newState, expected)
                state = newState
            case .failure(let error):
                XCTFail("Unexpected failure for \(trigger): \(error)")
            }
        }
    }

    func testStartFailedReturnsToIdle() {
        let result = RecordingStateMachine.transition(current: .starting, trigger: .startFailed)
        XCTAssertEqual(try? result.get(), .idle)
    }

    func testPauseFromIdleIsIllegal() {
        let result = RecordingStateMachine.transition(current: .idle, trigger: .pause)
        XCTAssertEqual(result, .failure(.illegalTransition(from: .idle, trigger: .pause)))
    }

    func testResumeFromRecordingIsIllegal() {
        let result = RecordingStateMachine.transition(current: .recording, trigger: .resume)
        XCTAssertEqual(result, .failure(.illegalTransition(from: .recording, trigger: .resume)))
    }

    func testStopFromPausedSucceeds() {
        let result = RecordingStateMachine.transition(current: .paused, trigger: .stop)
        XCTAssertEqual(try? result.get(), .stopping)
    }
}
