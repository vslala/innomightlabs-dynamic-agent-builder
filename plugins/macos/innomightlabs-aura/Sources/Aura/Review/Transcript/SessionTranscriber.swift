import Foundation
import WhisperKit

/// Produces a timestamped `Transcript` from a session's microphone track, on device.
///
/// Deliberately separate from the voice-control transcriber, which turns a buffer of samples
/// into a bare `String` for intent matching. That shape is useless here: the whole point of
/// this transcript is the timing, so segment and word boundaries are preserved rather than
/// joined away.
///
/// The model downloads from Hugging Face on first use and caches outside the app bundle, so
/// nothing is committed to the repo. `base` rather than the wake-word path's `tiny`, which is
/// tuned for short commands and too weak for narration.
actor SessionTranscriber {
    private static let model = "base"

    private var pipeline: WhisperKit?

    func transcribe(microphoneURL: URL) async throws -> Transcript {
        let pipeline = try await pipeline()

        let results = try await pipeline.transcribe(
            audioPath: microphoneURL.path,
            decodeOptions: DecodingOptions(wordTimestamps: true)
        )

        var segments: [Transcript.Segment] = []
        for segment in results.flatMap(\.segments) {
            let text = segment.text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else { continue }
            segments.append(Transcript.Segment(
                id: segments.count,
                start: TimeInterval(segment.start),
                end: TimeInterval(segment.end),
                text: text,
                words: segment.words?.map {
                    Transcript.Word(
                        start: TimeInterval($0.start),
                        end: TimeInterval($0.end),
                        text: $0.word.trimmingCharacters(in: .whitespaces)
                    )
                }
            ))
        }

        return Transcript(
            source: microphoneURL.lastPathComponent,
            engine: "whisperkit/openai_whisper-\(Self.model)",
            language: results.first?.language,
            segments: segments.sorted { $0.start < $1.start }
        )
    }

    private func pipeline() async throws -> WhisperKit {
        if let pipeline { return pipeline }
        let created = try await WhisperKit(WhisperKitConfig(model: Self.model))
        pipeline = created
        return created
    }
}
