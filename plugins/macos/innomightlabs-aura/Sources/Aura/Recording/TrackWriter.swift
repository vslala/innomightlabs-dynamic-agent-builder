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
    private let pauseClock = PauseClock()
    private let sessionStartTime: CMTime

    init(
        outputURL: URL,
        outputFileType: AVFileType,
        mediaType: AVMediaType,
        outputSettings: [String: Any],
        sessionStartTime: CMTime
    ) throws {
        self.sessionStartTime = sessionStartTime
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
            input.append(sampleBuffer)
        } else if let retimed = Self.retimed(sampleBuffer, newPresentationTime: adjustedPTS) {
            input.append(retimed)
        }
    }

    func finish(completion: @escaping @Sendable () -> Void) {
        input.markAsFinished()
        writer.finishWriting(completionHandler: completion)
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
