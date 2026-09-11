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

    /// - Parameter mediaDuration: the recording's length, used to discard the speech the
    ///   model hallucinates over trailing silence. Without it a run of `[BLANK_AUDIO]` can
    ///   land seconds past the end of the video and the agent will happily propose edits there.
    func transcribe(microphoneURL: URL, mediaDuration: TimeInterval? = nil) async throws -> Transcript {
        let pipeline = try await pipeline()

        let results = try await pipeline.transcribe(
            audioPath: microphoneURL.path,
            decodeOptions: DecodingOptions(wordTimestamps: true)
        )

        // Raw: `Transcript.normalized` does the cleaning, numbering, and clamping, so the
        // rules live in one tested place rather than here and there.
        let raw = results.flatMap(\.segments).map { segment in
            Transcript.Segment(
                id: 0,
                start: TimeInterval(segment.start),
                end: TimeInterval(segment.end),
                text: segment.text,
                words: (segment.words ?? []).map {
                    Transcript.Word(
                        id: 0,
                        start: TimeInterval($0.start),
                        end: TimeInterval($0.end),
                        text: $0.word
                    )
                }
            )
        }

        return Transcript(
            source: microphoneURL.lastPathComponent,
            engine: "whisperkit/openai_whisper-\(Self.model)",
            language: results.first?.language,
            segments: Transcript.normalized(segments: raw, mediaDuration: mediaDuration)
        )
    }

    private func pipeline() async throws -> WhisperKit {
        if let pipeline { return pipeline }
        let created = try await WhisperKit(WhisperKitConfig(model: Self.model))
        pipeline = created
        return created
    }
}
