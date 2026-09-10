import AVFoundation
import Foundation

/// Dictates an edit instruction: records a short clip while the user holds the mic button,
/// then transcribes it on device.
///
/// `AVAudioRecorder` rather than the capture-session plumbing used for recording, because all
/// that is needed here is a small file on disk — which is also exactly what WhisperKit takes.
@MainActor
final class VoiceInstructionRecorder: ObservableObject {
    enum State: Equatable {
        case idle
        case listening
        case transcribing
        case failed(String)
    }

    @Published private(set) var state: State = .idle

    private var recorder: AVAudioRecorder?
    private var fileURL: URL?
    private let transcriber = SessionTranscriber()

    /// Long enough for an instruction, short enough to bound a stuck recording.
    private static let maximumDuration: TimeInterval = 60

    func start() {
        guard state == .idle || isFailed else { return }

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-instruction-\(UUID().uuidString).m4a")
        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
            AVSampleRateKey: 44_100,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
        ]

        do {
            let recorder = try AVAudioRecorder(url: url, settings: settings)
            guard recorder.record(forDuration: Self.maximumDuration) else {
                state = .failed("Couldn't start the microphone.")
                return
            }
            self.recorder = recorder
            fileURL = url
            state = .listening
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    /// Stops, transcribes, and returns the text. Nil if nothing usable was captured.
    func finish() async -> String? {
        guard state == .listening, let recorder, let fileURL else { return nil }

        recorder.stop()
        self.recorder = nil
        state = .transcribing

        defer {
            try? FileManager.default.removeItem(at: fileURL)
            self.fileURL = nil
        }

        do {
            let transcript = try await transcriber.transcribe(microphoneURL: fileURL)
            let text = transcript.segments
                .map(\.text)
                .joined(separator: " ")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            state = .idle
            return text.isEmpty ? nil : text
        } catch {
            state = .failed(error.localizedDescription)
            return nil
        }
    }

    func cancel() {
        recorder?.stop()
        recorder = nil
        if let fileURL {
            try? FileManager.default.removeItem(at: fileURL)
        }
        fileURL = nil
        state = .idle
    }

    private var isFailed: Bool {
        if case .failed = state { return true }
        return false
    }
}
