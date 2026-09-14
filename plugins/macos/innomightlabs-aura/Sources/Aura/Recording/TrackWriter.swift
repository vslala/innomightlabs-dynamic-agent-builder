import AVFoundation
import CoreMedia

/// Wraps a single `AVAssetWriter`/`AVAssetWriterInput` pair for one output file,
/// dropping/rebasing samples via `PauseClock` so pause/resume never touches the
/// underlying capture session.
///
/// `append` is called from one dedicated capture queue per track; `pause`/`resume`
/// are called from the main actor. `PauseClock` is the only mutable shared state and
/// is internally lock-protected, so this type is safe to share across those threads.
final class TrackWriter: @unchecked Sendable {
    private let writer: AVAssetWriter
    private let input: AVAssetWriterInput
    private let pauseClock: PauseClock
    private let sessionStartTime: CMTime

    /// The file this writer is producing. Read back by `RecordingController` to name the
    /// `track_start` event this writer's segment logs, since a segmented track needs that
    /// event keyed by file rather than by kind.
    let outputURL: URL

    private let firstSampleLock = NSLock()
    private var _firstAppendedHostTime: CMTime?

    /// Where the first sample this track accepted landed on the pause-compacted timeline.
    ///
    /// Capture sources warm up at different speeds, and `AVAssetWriter` only preserves that
    /// offset for video (as a leading empty edit) — for audio it slides the first sample to
    /// time zero and throws the offset away, which desynchronises audio from video by the
    /// whole warm-up delay. Recording it here is what lets the review layer put the track
    /// back where it belongs.
    ///
    /// This is the *rebased* timestamp, not the raw one: if the recording was paused before
    /// this track produced anything, the raw time would include the paused span that the file
    /// itself does not contain.
    var firstAppendedHostTime: CMTime? {
        firstSampleLock.lock()
        defer { firstSampleLock.unlock() }
        return _firstAppendedHostTime
    }

    init(
        outputURL: URL,
        outputFileType: AVFileType,
        mediaType: AVMediaType,
        outputSettings: [String: Any],
        sessionStartTime: CMTime,
        elapsedPausedDuration: CMTime = .zero
    ) throws {
        self.outputURL = outputURL
        self.sessionStartTime = sessionStartTime
        pauseClock = PauseClock(accumulatedPausedDuration: elapsedPausedDuration)
        writer = try AVAssetWriter(outputURL: outputURL, fileType: outputFileType)
        input = AVAssetWriterInput(mediaType: mediaType, outputSettings: outputSettings)
        input.expectsMediaDataInRealTime = true
        guard writer.canAdd(input) else {
            throw RecordingError.writerSetupFailed("Cannot add \(mediaType.rawValue) input for \(outputURL.lastPathComponent)")
        }
        writer.add(input)
    }

    func start() throws {
        guard writer.startWriting() else {
            throw RecordingError.writerSetupFailed(
                writer.error?.localizedDescription ?? "unknown startWriting failure"
            )
        }
        writer.startSession(atSourceTime: sessionStartTime)
    }

    /// Non-nil once the writer has entered `.failed` status (e.g. an `append` was
    /// rejected downstream) — checked after `finish()` completes.
    var failureReason: String? {
        guard writer.status == .failed else { return nil }
        return writer.error?.localizedDescription ?? "Unknown failure writing \(writer.outputURL.lastPathComponent)"
    }

    func pause(at hostTime: CMTime) {
        pauseClock.pause(at: hostTime)
    }

    func resume(at hostTime: CMTime) {
        pauseClock.resume(at: hostTime)
    }

    func append(_ sampleBuffer: CMSampleBuffer) {
        guard input.isReadyForMoreMediaData else { return }

        let originalPTS = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        guard let adjustedPTS = pauseClock.adjustedTime(for: originalPTS) else {
            return
        }

        if adjustedPTS == originalPTS {
            guard input.append(sampleBuffer) else { return }
        } else if let retimed = Self.retimed(sampleBuffer, newPresentationTime: adjustedPTS) {
            guard input.append(retimed) else { return }
        } else {
            return
        }

        firstSampleLock.lock()
        if _firstAppendedHostTime == nil {
            _firstAppendedHostTime = adjustedPTS
        }
        firstSampleLock.unlock()
    }

    func finish(completion: @escaping @Sendable () -> Void) {
        input.markAsFinished()
        writer.finishWriting(completionHandler: completion)
    }

    /// Aborts writing without finalizing the output file. Unlike `finish`, `cancelWriting()`
    /// handles its own finalization — do not call `markAsFinished()` first.
    func cancel() {
        writer.cancelWriting()
    }

    private static func retimed(_ sampleBuffer: CMSampleBuffer, newPresentationTime: CMTime) -> CMSampleBuffer? {
        var count: CMItemCount = 0
        CMSampleBufferGetSampleTimingInfoArray(sampleBuffer, entryCount: 0, arrayToFill: nil, entriesNeededOut: &count)
        guard count > 0 else { return nil }

        var timingInfos = [CMSampleTimingInfo](repeating: CMSampleTimingInfo(), count: count)
        CMSampleBufferGetSampleTimingInfoArray(sampleBuffer, entryCount: count, arrayToFill: &timingInfos, entriesNeededOut: nil)

        let delta = newPresentationTime - CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        for index in timingInfos.indices {
            timingInfos[index].presentationTimeStamp = timingInfos[index].presentationTimeStamp + delta
        }

        var retimedBuffer: CMSampleBuffer?
        CMSampleBufferCreateCopyWithNewTiming(
            allocator: kCFAllocatorDefault,
            sampleBuffer: sampleBuffer,
            sampleTimingEntryCount: timingInfos.count,
            sampleTimingArray: &timingInfos,
            sampleBufferOut: &retimedBuffer
        )
        return retimedBuffer
    }
}
