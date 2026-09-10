import Foundation

/// Builds the message sent to the agent.
///
/// Pure and unit-tested, because this is where the feature is won or lost: the agent can only
/// propose sound edits if it is told the operation vocabulary exactly, and told the transcript
/// in the same clock the operations are expressed in.
enum EditSuggestionPrompt {
    /// Kept well under the point where a long recording's transcript would crowd out the
    /// instruction itself.
    static let maximumTranscriptCues = 400

    static func build(instruction: String, context: EditSuggestionContext) -> String {
        var sections: [String] = []

        sections.append("""
        You are editing a screen recording inside Aura. Propose edits as JSON operations.

        Reply with a short sentence explaining what you propose, then a JSON array of \
        operations in a ```json fenced block. Use an empty array if no edit is warranted, or \
        if the request is unclear — say so rather than guessing.

        All times are seconds on the recording's own timeline (not the edited timeline), and \
        match the transcript timestamps below. The recording is \
        \(String(format: "%.2f", context.duration))s long.

        Available operations:
        {"op":"remove_range","start":<s>,"end":<s>}  - cut this span out
        {"op":"split_clip","t":<s>}                  - split without removing anything
        {"op":"set_overlay_keyframe","t":<s>,"rect":{"x":0-1,"y":0-1,"width":0-1,"height":0-1},"visible":<bool>}
                                                     - move/resize/hide the camera from t onwards
        {"op":"remove_overlay_keyframe","t":<s>}
        {"op":"set_lane_gain","lane":"microphone"|"system_audio","t":<s>,"gain":0-1}
        {"op":"set_lane_muted","lane":"microphone"|"system_audio","muted":<bool>}
        {"op":"set_lane_offset","lane":"microphone"|"system_audio","seconds":<-5..5>}
                                                     - nudge audio sync

        You may add a "why" string to any operation to explain it.
        Only remove_range removes content. Never propose removing the whole recording.
        """)

        sections.append(currentState(context))

        if let transcript = context.transcript, !transcript.segments.isEmpty {
            sections.append(transcriptSection(transcript, micTimeOffset: context.document.micTimeOffset))
        } else {
            sections.append("Transcript: not available for this recording.")
        }

        if !context.markers.isEmpty {
            let markers = context.markers
                .map { String(format: "%.2f: %@", $0.time, $0.label) }
                .joined(separator: "\n")
            sections.append("Markers the user flagged while recording:\n\(markers)")
        }

        sections.append("Request:\n\(instruction.trimmingCharacters(in: .whitespacesAndNewlines))")

        return sections.joined(separator: "\n\n")
    }

    /// Told explicitly, so the agent proposes changes relative to the edit as it stands rather
    /// than to the original recording.
    private static func currentState(_ context: EditSuggestionContext) -> String {
        let document = context.document
        let clips = document.clips
            .map { String(format: "%.2f-%.2f", $0.source.start, $0.source.end) }
            .joined(separator: ", ")

        var lines = ["Current edit:", "  kept spans: \(clips.isEmpty ? "none" : clips)"]

        for keyframe in document.cameraOverlay.sorted(by: { $0.t < $1.t }) {
            lines.append(String(
                format: "  camera at %.2fs: %@ rect %.2f,%.2f %.2fx%.2f",
                keyframe.t,
                keyframe.visible ? "visible" : "hidden",
                keyframe.rect.x, keyframe.rect.y, keyframe.rect.width, keyframe.rect.height
            ))
        }

        for lane in document.audioLanes {
            lines.append(String(
                format: "  %@: %@, slip %+.0fms",
                lane.lane.rawValue,
                lane.muted ? "muted" : "unmuted",
                lane.offset * 1000
            ))
        }

        return lines.joined(separator: "\n")
    }

    private static func transcriptSection(_ transcript: Transcript, micTimeOffset: TimeInterval) -> String {
        let cues = transcript.segments.prefix(maximumTranscriptCues).map { segment in
            // Shifted into recording time, which is the clock the operations use — the
            // transcript itself is stamped in the microphone file's own clock.
            String(
                format: "%.2f-%.2f %@",
                segment.start + micTimeOffset,
                segment.end + micTimeOffset,
                segment.text
            )
        }

        var section = "Transcript (start-end text):\n" + cues.joined(separator: "\n")
        if transcript.segments.count > maximumTranscriptCues {
            section += "\n… \(transcript.segments.count - maximumTranscriptCues) further cues omitted."
        }
        return section
    }
}
