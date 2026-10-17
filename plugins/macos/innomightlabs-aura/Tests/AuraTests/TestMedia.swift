import AVFoundation
import XCTest

/// Real, decodable media for tests that build compositions, so what AVFoundation accepts is
/// proven rather than assumed.
enum TestMedia {
    /// A blank-picture 160×90 movie. A low frame rate by default: these tests care that frames
    /// exist, not how many, and encoding fewer keeps them quick.
    static func writeVideo(to url: URL, seconds: Int, framesPerSecond: Int = 10) async throws {
        let writer = try AVAssetWriter(outputURL: url, fileType: .mov)
        let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
            AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: 160, AVVideoHeightKey: 90
        ])
        input.expectsMediaDataInRealTime = false
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: nil)
        writer.add(input)
        writer.startWriting()
        writer.startSession(atSourceTime: .zero)

        var pixels: CVPixelBuffer?
        CVPixelBufferCreate(kCFAllocatorDefault, 160, 90, kCVPixelFormatType_32BGRA, nil, &pixels)
        let buffer = try XCTUnwrap(pixels)
        for frame in 0..<(seconds * framesPerSecond) {
            while !input.isReadyForMoreMediaData { try await Task.sleep(for: .milliseconds(2)) }
            adaptor.append(buffer, withPresentationTime: CMTime(value: CMTimeValue(frame), timescale: CMTimeScale(framesPerSecond)))
        }
        input.markAsFinished()
        await writer.finishWriting()
    }

    /// Silent mono AAC, the codec and container the recorder writes.
    static func writeSilentAudio(to url: URL, seconds: Double) throws {
        let rate = 44_100.0
        let file = try AVAudioFile(forWriting: url, settings: [
            AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: rate, AVNumberOfChannelsKey: 1
        ])
        let format = AVAudioFormat(standardFormatWithSampleRate: rate, channels: 1)!
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(rate * seconds))!
        buffer.frameLength = buffer.frameCapacity
        try file.write(from: buffer)
    }
}
