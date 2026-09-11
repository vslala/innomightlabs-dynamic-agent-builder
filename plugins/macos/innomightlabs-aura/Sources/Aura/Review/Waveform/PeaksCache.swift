import Foundation

/// Binary cache for a waveform envelope, stored beside the audio it describes.
///
/// Binary rather than JSON because it is a UI cache nobody reads: 180k buckets of three
/// floats is roughly 5MB of text and a couple of hundred milliseconds to parse, against a
/// ~2MB blob and a single read. Invalidation is the source file's size and modification date
/// in the header — no separate index to keep in step.
enum PeaksCache {
    private static let magic = Array("AURAPEAK".utf8)
    /// v2 added the per-bucket RMS band. A v1 blob is rejected and re-extracted.
    private static let formatVersion: UInt32 = 2

    struct SourceStamp: Equatable {
        let size: UInt64
        let modified: Int64

        init(size: UInt64, modified: Int64) {
            self.size = size
            self.modified = modified
        }

        /// Read through `FileManager` rather than `URL.resourceValues`, which caches its
        /// answers on the URL instance — a rewritten file would keep reporting its old size
        /// and the stale cache would be accepted.
        init?(url: URL) {
            guard
                let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
                let size = attributes[.size] as? NSNumber,
                let modified = attributes[.modificationDate] as? Date
            else { return nil }
            self.size = size.uint64Value
            self.modified = Int64((modified.timeIntervalSince1970 * 1000).rounded())
        }
    }

    // MARK: - Pure encoding

    static func encode(_ peaks: WaveformPeaks, stamp: SourceStamp) -> Data {
        var data = Data(magic)
        data.append(contentsOf: littleEndianBytes(formatVersion))
        data.append(contentsOf: littleEndianBytes(stamp.size))
        data.append(contentsOf: littleEndianBytes(UInt64(bitPattern: stamp.modified)))
        data.append(contentsOf: littleEndianBytes(UInt32(peaks.bucketsPerSecond)))
        data.append(contentsOf: littleEndianBytes(UInt32(peaks.bucketCount)))

        for index in 0..<peaks.bucketCount {
            data.append(contentsOf: littleEndianBytes(peaks.minima[index].bitPattern))
            data.append(contentsOf: littleEndianBytes(peaks.maxima[index].bitPattern))
            data.append(contentsOf: littleEndianBytes(peaks.rms[index].bitPattern))
        }
        for covered in peaks.coverage {
            data.append(covered ? 1 : 0)
        }

        return data
    }

    /// Returns nil for anything that isn't a cache written by this build for this exact
    /// source file — a truncated blob included.
    static func decode(_ data: Data, expecting stamp: SourceStamp) -> WaveformPeaks? {
        var cursor = 0

        func read(_ count: Int) -> Data? {
            guard cursor + count <= data.count else { return nil }
            defer { cursor += count }
            return data.subdata(in: (data.startIndex + cursor)..<(data.startIndex + cursor + count))
        }

        guard let header = read(magic.count), Array(header) == magic else { return nil }
        guard
            let version: UInt32 = read(4).flatMap(value),
            version == formatVersion,
            let size: UInt64 = read(8).flatMap(value),
            let modified: UInt64 = read(8).flatMap(value),
            let bucketsPerSecond: UInt32 = read(4).flatMap(value),
            let bucketCount: UInt32 = read(4).flatMap(value)
        else { return nil }

        guard SourceStamp(size: size, modified: Int64(bitPattern: modified)) == stamp else { return nil }

        let count = Int(bucketCount)
        var minima: [Float] = []
        var maxima: [Float] = []
        var rms: [Float] = []
        minima.reserveCapacity(count)
        maxima.reserveCapacity(count)
        rms.reserveCapacity(count)

        for _ in 0..<count {
            guard
                let low: UInt32 = read(4).flatMap(value),
                let high: UInt32 = read(4).flatMap(value),
                let mean: UInt32 = read(4).flatMap(value)
            else { return nil }
            minima.append(Float(bitPattern: low))
            maxima.append(Float(bitPattern: high))
            rms.append(Float(bitPattern: mean))
        }

        guard let coverageBytes = read(count) else { return nil }

        return WaveformPeaks(
            bucketsPerSecond: Int(bucketsPerSecond),
            minima: minima,
            maxima: maxima,
            rms: rms,
            coverage: coverageBytes.map { $0 != 0 }
        )
    }

    // MARK: - File access

    static func load(cacheURL: URL, sourceURL: URL) -> WaveformPeaks? {
        guard
            let stamp = SourceStamp(url: sourceURL),
            let data = try? Data(contentsOf: cacheURL)
        else { return nil }
        return decode(data, expecting: stamp)
    }

    static func store(_ peaks: WaveformPeaks, cacheURL: URL, sourceURL: URL) {
        guard peaks.bucketCount > 0, let stamp = SourceStamp(url: sourceURL) else { return }
        try? encode(peaks, stamp: stamp).write(to: cacheURL, options: .atomic)
    }

    // MARK: - Byte plumbing

    private static func littleEndianBytes<T: FixedWidthInteger>(_ value: T) -> [UInt8] {
        withUnsafeBytes(of: value.littleEndian) { Array($0) }
    }

    private static func value<T: FixedWidthInteger>(_ data: Data) -> T? {
        guard data.count == MemoryLayout<T>.size else { return nil }
        return T(littleEndian: data.withUnsafeBytes { $0.loadUnaligned(as: T.self) })
    }
}
