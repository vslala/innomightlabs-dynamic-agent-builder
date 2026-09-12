import CoreGraphics
import Foundation

/// Binary on-disk cache for a track's filmstrip, following `PeaksCache`.
///
/// Binary rather than JSON for the same reason: one `Data(contentsOf:)` and no parse, where a
/// base64-in-JSON encoding of 600 JPEGs would be several megabytes of text to decode on every
/// window open.
///
/// Not a sprite sheet either. 600 frames at 160px wide is a 96,000px image, past what can be
/// decoded as a single texture — so frames are stored individually behind an index.
///
/// Validation is the whole invalidation story: the header carries the source file's size and
/// modification time, and a mismatch means re-extract.
enum FilmstripCache {
    private static let magic: UInt32 = 0x41_46_53_31 // "AFS1"
    private static let formatVersion: UInt16 = 1

    struct SourceStamp: Equatable, Sendable {
        let fileSize: UInt64
        let modified: TimeInterval

        init(fileSize: UInt64, modified: TimeInterval) {
            self.fileSize = fileSize
            self.modified = modified
        }

        init?(url: URL) {
            guard
                let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
                let size = attributes[.size] as? NSNumber,
                let date = attributes[.modificationDate] as? Date
            else { return nil }
            fileSize = size.uint64Value
            modified = date.timeIntervalSince1970
        }
    }

    // MARK: - Encoding

    static func encode(_ strip: Filmstrip, stamp: SourceStamp) -> Data {
        var data = Data()
        data.append(contentsOf: withUnsafeBytes(of: magic.littleEndian) { Array($0) })
        data.append(contentsOf: withUnsafeBytes(of: formatVersion.littleEndian) { Array($0) })
        data.append(contentsOf: withUnsafeBytes(of: stamp.fileSize.littleEndian) { Array($0) })
        data.append(contentsOf: withUnsafeBytes(of: stamp.modified.bitPattern.littleEndian) { Array($0) })
        data.append(contentsOf: withUnsafeBytes(of: strip.interval.bitPattern.littleEndian) { Array($0) })
        data.append(contentsOf: withUnsafeBytes(of: UInt32(strip.frameSize.width).littleEndian) { Array($0) })
        data.append(contentsOf: withUnsafeBytes(of: UInt32(strip.frameSize.height).littleEndian) { Array($0) })
        data.append(contentsOf: withUnsafeBytes(of: UInt32(strip.frames.count).littleEndian) { Array($0) })

        // Lengths first, so a reader can slice without scanning.
        for frame in strip.frames {
            data.append(contentsOf: withUnsafeBytes(of: UInt32(frame.count).littleEndian) { Array($0) })
        }
        for frame in strip.frames {
            data.append(frame)
        }
        return data
    }

    // MARK: - Decoding

    static func decode(_ data: Data, expecting stamp: SourceStamp?) -> Filmstrip? {
        var cursor = 0

        func read<T>(_ type: T.Type) -> T? {
            let size = MemoryLayout<T>.size
            guard cursor + size <= data.count else { return nil }
            let value = data.subdata(in: cursor..<(cursor + size)).withUnsafeBytes {
                $0.loadUnaligned(as: T.self)
            }
            cursor += size
            return value
        }

        guard let fileMagic = read(UInt32.self), UInt32(littleEndian: fileMagic) == magic else { return nil }
        guard let version = read(UInt16.self), UInt16(littleEndian: version) == formatVersion else { return nil }
        guard let size = read(UInt64.self), let modifiedBits = read(UInt64.self) else { return nil }
        guard let intervalBits = read(UInt64.self) else { return nil }
        guard let width = read(UInt32.self), let height = read(UInt32.self) else { return nil }
        guard let count = read(UInt32.self) else { return nil }

        if let stamp {
            let onDisk = SourceStamp(
                fileSize: UInt64(littleEndian: size),
                modified: Double(bitPattern: UInt64(littleEndian: modifiedBits))
            )
            guard onDisk == stamp else { return nil }
        }

        let frameCount = Int(UInt32(littleEndian: count))
        guard frameCount >= 0, frameCount <= Filmstrip.maxFrames else { return nil }

        var lengths: [Int] = []
        lengths.reserveCapacity(frameCount)
        for _ in 0..<frameCount {
            guard let length = read(UInt32.self) else { return nil }
            lengths.append(Int(UInt32(littleEndian: length)))
        }

        var frames: [Data] = []
        frames.reserveCapacity(frameCount)
        for length in lengths {
            guard cursor + length <= data.count else { return nil }
            frames.append(data.subdata(in: cursor..<(cursor + length)))
            cursor += length
        }

        return Filmstrip(
            interval: Double(bitPattern: UInt64(littleEndian: intervalBits)),
            frameSize: CGSize(
                width: CGFloat(UInt32(littleEndian: width)),
                height: CGFloat(UInt32(littleEndian: height))
            ),
            frames: frames
        )
    }

    // MARK: - Files

    static func load(from url: URL, source: URL) -> Filmstrip? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return decode(data, expecting: SourceStamp(url: source))
    }

    static func write(_ strip: Filmstrip, to url: URL, source: URL) {
        guard let stamp = SourceStamp(url: source) else { return }
        try? encode(strip, stamp: stamp).write(to: url, options: .atomic)
    }
}
