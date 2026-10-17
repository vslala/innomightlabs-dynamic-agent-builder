import XCTest
import AVFoundation
@testable import Aura

final class VoiceSampleExtractorTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-sample-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    /// A 44.1 kHz mono recording whose first half is silent and second half is a loud tone, so
    /// the extracted clip's content shows where it was cut from.
    private func recording(seconds: Double = 10) throws -> URL {
        let rate = 44_100.0
        let url = directory.appendingPathComponent("mic.m4a")
        let file = try AVAudioFile(forWriting: url, settings: [
            AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: rate, AVNumberOfChannelsKey: 1
        ])
        let format = AVAudioFormat(standardFormatWithSampleRate: rate, channels: 1)!
        let frames = AVAudioFrameCount(rate * seconds)
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames)!
        buffer.frameLength = frames
        for index in 0..<Int(frames) {
            buffer.floatChannelData![0][index] = index < Int(frames) / 2
                ? 0 : 0.5 * Float(sin(2 * Double.pi * 440 * Double(index) / rate))
        }
        try file.write(from: buffer)
        return url
    }

    func testWritesAMono24kHzClipOfTheRequestedLengthWithTheReferenceText() throws {
        let source = try recording()
        let destination = directory.appendingPathComponent("replacements/sample.wav")
        let reference = VoiceReference(start: 6, end: 9, text: "hello there")

        let sample = try VoiceSampleExtractor.extract(reference, from: source, to: destination)

        XCTAssertEqual(sample.text, "hello there")
        let file = try AVAudioFile(forReading: sample.audioURL)
        XCTAssertEqual(file.processingFormat.sampleRate, 24_000)
        XCTAssertEqual(file.processingFormat.channelCount, 1)
        XCTAssertEqual(Double(file.length) / 24_000, 3, accuracy: 0.05)
    }

    func testTheClipComesFromTheRequestedPartOfTheRecording() throws {
        let source = try recording()
        let loud = try VoiceSampleExtractor.extract(
            VoiceReference(start: 6, end: 9, text: "x"), from: source, to: directory.appendingPathComponent("loud.wav")
        )
        let quiet = try VoiceSampleExtractor.extract(
            VoiceReference(start: 1, end: 4, text: "x"), from: source, to: directory.appendingPathComponent("quiet.wav")
        )

        XCTAssertGreaterThan(try peak(of: loud.audioURL), 0.3)
        XCTAssertLessThan(try peak(of: quiet.audioURL), 0.01)
    }

    func testAStretchPastTheEndOfTheRecordingIsRefused() throws {
        let source = try recording(seconds: 5)
        XCTAssertThrowsError(try VoiceSampleExtractor.extract(
            VoiceReference(start: 3, end: 9, text: "x"), from: source, to: directory.appendingPathComponent("x.wav")
        )) {
            XCTAssertEqual($0 as? VoiceSampleExtractor.ExtractionError, .outsideRecording)
        }
    }

    func testAMissingRecordingFails() {
        XCTAssertThrowsError(try VoiceSampleExtractor.extract(
            VoiceReference(start: 0, end: 6, text: "x"),
            from: directory.appendingPathComponent("nope.m4a"),
            to: directory.appendingPathComponent("x.wav")
        ))
    }

    private func peak(of url: URL) throws -> Float {
        let file = try AVAudioFile(forReading: url)
        let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length))!
        try file.read(into: buffer)
        return UnsafeBufferPointer(start: buffer.floatChannelData![0], count: Int(buffer.frameLength)).map(abs).max() ?? 0
    }
}
