import CoreMedia

/// Rebases sample timestamps so that paused wall-clock time is excluded from the
/// recorded output entirely, rather than leaving a frozen-frame/silence gap.
///
/// `pause`/`resume` are called from the main actor while `adjustedTime` is read from
/// a capture queue for every sample buffer, so all access is serialized behind a lock.
final class PauseClock: @unchecked Sendable {
    private let lock = NSLock()
    private var accumulatedPausedDuration: CMTime = .zero
    private var pauseStartedAt: CMTime?

    var isPaused: Bool {
        lock.lock()
        defer { lock.unlock() }
        return pauseStartedAt != nil
    }

    func pause(at hostTime: CMTime) {
        lock.lock()
        defer { lock.unlock() }
        guard pauseStartedAt == nil else { return }
        pauseStartedAt = hostTime
    }

    func resume(at hostTime: CMTime) {
        lock.lock()
        defer { lock.unlock() }
        guard let pauseStartedAt else { return }
        accumulatedPausedDuration = accumulatedPausedDuration + (hostTime - pauseStartedAt)
        self.pauseStartedAt = nil
    }

    /// Returns the rebased time samples should be written at, or `nil` if the sample
    /// arrived while paused and should be dropped entirely.
    func adjustedTime(for hostTime: CMTime) -> CMTime? {
        lock.lock()
        defer { lock.unlock() }
        if pauseStartedAt != nil {
            return nil
        }
        return hostTime - accumulatedPausedDuration
    }
}
