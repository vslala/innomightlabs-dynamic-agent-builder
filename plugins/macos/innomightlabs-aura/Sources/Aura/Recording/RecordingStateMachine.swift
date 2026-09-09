enum RecordingEventTrigger: Equatable {
    case start
    case didStart
    case startFailed
    case pause
    case resume
    case stop
    case cancel
    case didStop
}

enum RecordingStateError: Error, Equatable {
    case illegalTransition(from: RecordingState, trigger: RecordingEventTrigger)
}

enum RecordingStateMachine {
    static func transition(
        current: RecordingState,
        trigger: RecordingEventTrigger
    ) -> Result<RecordingState, RecordingStateError> {
        switch (current, trigger) {
        case (.idle, .start):
            return .success(.starting)
        case (.starting, .didStart):
            return .success(.recording)
        case (.starting, .startFailed):
            return .success(.idle)
        case (.recording, .pause):
            return .success(.paused)
        case (.paused, .resume):
            return .success(.recording)
        case (.recording, .stop), (.paused, .stop):
            return .success(.stopping)
        case (.starting, .cancel), (.recording, .cancel), (.paused, .cancel):
            return .success(.stopping)
        case (.stopping, .didStop):
            return .success(.idle)
        default:
            return .failure(.illegalTransition(from: current, trigger: trigger))
        }
    }
}
