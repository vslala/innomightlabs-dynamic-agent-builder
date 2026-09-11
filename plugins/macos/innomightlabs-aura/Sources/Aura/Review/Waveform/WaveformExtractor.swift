import AVFoundation
import CoreMedia
import Foundation

/// Decodes an audio file into a peak envelope.
///
/// An `actor` because `AVAssetReader` is non-Sendable and serializes internally anyway; it
/// publishes only Sendable values, so nothing AVFoundation-shaped escapes.
actor WaveformExtractor {
    /// Asking AVFoundation for one channel is the single biggest simplification here — no
    /// mixdown code and half the data touched.
    private static let sampleRate: Double = 44_100
    private static let channelCount = 1

    private static var outputSettings: [String: Any] {
        [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVLinearPCMBitDepthKey: 32,
            AVLinearPCMIsFloatKey: true,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsNonInterleaved: false,
            AVSampleRateKey: sampleRate,
            AVNumberOfChannelsKey: channelCount
        ]
    }

    /// Streams the file rather than materializing PCM: mono float32 at 44.1kHz for half an
    /// hour would be ~317MB, while the bucket arrays for the same recording are ~2MB.
    /// A partial envelope plus whether it is the whole file. Cancellation returns what was
    /// decoded so the lane can still draw, but the caller must not cache it.
    struct Extraction: Sendable {
        let peaks: WaveformPeaks
        let isComplete: Bool
    }

    func extract(
        url: URL,
        duration: CMTime,
        bucketsPerSecond: Int = WaveformPeaks.defaultBucketsPerSecond
    ) async -> Extraction {
        let seconds = Timeline.seconds(duration)
        guard seconds > 0 else { return Extraction(peaks: .empty, isComplete: false) }

        let asset = AVURLAsset(url: url, options: [AVURLAssetPreferPreciseDurationAndTimingKey: true])
        guard
            let track = try? await asset.loadTracks(withMediaType: .audio).first,
            let reader = try? AVAssetReader(asset: asset)
        else { return Extraction(peaks: .empty, isComplete: false) }

        let output = AVAssetReaderTrackOutput(track: track, outputSettings: Self.outputSettings)
        // The buffers are consumed in place, so a copy per buffer would be wasted work.
        output.alwaysCopiesSampleData = false
        guard reader.canAdd(output) else { return Extraction(peaks: .empty, isComplete: false) }
        reader.add(output)
        guard reader.startReading() else { return Extraction(peaks: .empty, isComplete: false) }

        var accumulator = PeakAccumulator(
            bucketCount: Int((seconds * Double(bucketsPerSecond)).rounded(.up)),
            samplesPerBucket: Self.sampleRate / Double(bucketsPerSecond),
            bucketsPerSecond: bucketsPerSecond
        )

        while let sample = output.copyNextSampleBuffer() {
            if Task.isCancelled {
                reader.cancelReading()
                // Incomplete: the tail buckets are simply unwritten, which is
                // indistinguishable from a muted span once it reaches the cache.
                return Extraction(peaks: accumulator.finish(), isComplete: false)
            }

            // Position by presentation timestamp, never by a running sample count. Muting
            // during recording leaves an empty edit, and the reader honours it by jumping the
            // timestamp across the gap rather than emitting silence — so counting samples
            // would smear the whole waveform earlier by the total muted duration.
            let pts = sample.presentationTimeStamp
            guard pts.isNumeric else { continue }
            let firstSampleIndex = Int((CMTimeGetSeconds(pts) * Self.sampleRate).rounded())

            try? sample.withAudioBufferList { bufferList, _ in
                for buffer in bufferList {
                    guard let data = buffer.mData else { continue }
                    let count = Int(buffer.mDataByteSize) / MemoryLayout<Float>.size
                    let samples = UnsafeBufferPointer(
                        start: data.assumingMemoryBound(to: Float.self),
                        count: count
                    )
                    accumulator.accumulate(
                        samples,
                        channelCount: Int(buffer.mNumberChannels),
                        firstSampleIndex: firstSampleIndex
                    )
                }
            }
        }

        return Extraction(peaks: accumulator.finish(), isComplete: reader.status == .completed)
    }

    /// High-resolution peaks for one window of the file.
    ///
    /// The cached envelope is 10ms per bucket, which is plenty when the whole recording is on
    /// screen but only ~25 data points across a quarter-second zoom — so it draws as a row of
    /// steps rather than a waveform, and there is nothing to aim a cut at. This re-reads just
    /// the visible window at whatever resolution the display can show, which is cheap because
    /// the window is short: a second of mono audio is 44k samples.
    func detail(
        url: URL,
        range: TimeSpan,
        bucketsPerSecond: Int
    ) async -> WaveformPeaks? {
        guard range.duration > 0, bucketsPerSecond > 0 else { return nil }

        let asset = AVURLAsset(url: url, options: [AVURLAssetPreferPreciseDurationAndTimingKey: true])
        guard
            let track = try? await asset.loadTracks(withMediaType: .audio).first,
            let reader = try? AVAssetReader(asset: asset)
        else { return nil }

        // Reading only the window is what keeps this affordable at any zoom level.
        reader.timeRange = CMTimeRange(
            start: Timeline.time(seconds: range.start),
            end: Timeline.time(seconds: range.end)
        )

        let output = AVAssetReaderTrackOutput(track: track, outputSettings: Self.outputSettings)
        output.alwaysCopiesSampleData = false
        guard reader.canAdd(output) else { return nil }
        reader.add(output)
        guard reader.startReading() else { return nil }

        var accumulator = PeakAccumulator(
            bucketCount: Int((range.duration * Double(bucketsPerSecond)).rounded(.up)),
            samplesPerBucket: Self.sampleRate / Double(bucketsPerSecond),
            bucketsPerSecond: bucketsPerSecond
        )

        while let sample = output.copyNextSampleBuffer() {
            if Task.isCancelled {
                reader.cancelReading()
                return nil
            }

            let pts = sample.presentationTimeStamp
            guard pts.isNumeric else { continue }
            // Relative to the window's start, since that is where these buckets begin.
            let offset = CMTimeGetSeconds(pts) - range.start
            let firstSampleIndex = Int((offset * Self.sampleRate).rounded())

            try? sample.withAudioBufferList { bufferList, _ in
                for buffer in bufferList {
                    guard let data = buffer.mData else { continue }
                    let count = Int(buffer.mDataByteSize) / MemoryLayout<Float>.size
                    accumulator.accumulate(
                        UnsafeBufferPointer(start: data.assumingMemoryBound(to: Float.self), count: count),
                        channelCount: Int(buffer.mNumberChannels),
                        firstSampleIndex: firstSampleIndex
                    )
                }
            }
        }

        return accumulator.finish()
    }

    /// Reads from the cache if it is still valid for the source file, otherwise extracts and
    /// caches. The cache is what makes reopening a session instant.
    ///
    /// Only a complete extraction is cached. Caching a cancelled one would be permanent:
    /// its stamp still matches the source, so every later open would accept an envelope that
    /// is blank after the point the user happened to close the window.
    func peaks(for url: URL, cacheURL: URL, duration: CMTime) async -> WaveformPeaks {
        if let cached = PeaksCache.load(cacheURL: cacheURL, sourceURL: url) {
            return cached
        }
        let extraction = await extract(url: url, duration: duration)
        if extraction.isComplete {
            PeaksCache.store(extraction.peaks, cacheURL: cacheURL, sourceURL: url)
        }
        return extraction.peaks
    }
}
