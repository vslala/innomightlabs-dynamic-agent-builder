import Foundation

/// Builds the message sent to the agent.
///
/// Pure and unit-tested, because this is where the feature is won or lost. The agent can only
/// propose sound edits if it is told the operation vocabulary exactly and shown the recording
/// in the same clock those operations use — and the whole thing has to fit inside the A2A
/// message cap alongside the user's request.
enum EditSuggestionPrompt {
    /// Reserved for the instructions, vocabulary, and the user's request, so the digest gets
    /// whatever is left. Generous, since going over is a hard rejection by the server.
    static let overheadAllowance = 4_000

    static func build(
        instruction: String,
        context: EditSuggestionContext,
        characterBudget: Int
    ) -> String {
        let request = instruction.trimmingCharacters(in: .whitespacesAndNewlines)
        let digestBudget = max(500, characterBudget - overheadAllowance - request.count)

        let digest = (context.digest ?? SessionDigest.make(
            sessionID: context.sessionID,
            duration: context.duration,
            probes: [],
            events: EventTimeline(events: []),
            document: context.document,
            transcript: context.transcript
        )).fitting(characterBudget: digestBudget)

        return """
        You are the editing assistant inside Aura, a screen recorder. You are given a digest of
        one recording and asked to change it. Propose changes as JSON operations.

        Reply with one or two sentences explaining what you propose, then a JSON array of
        operations in a ```json fenced block. Use an empty array when no edit is warranted, or
        when the request is unclear — ask rather than guess.

        Reason only from the digest below. It describes this recording and no other.

        All times are seconds on the recording's own timeline, matching `transcript` in the
        digest — not the shortened timeline that results from cuts. `keptSpans` tells you what
        currently survives; propose changes relative to that.

        Operations:
        {"op":"remove_range","start":<s>,"end":<s>}   cut this span out
        {"op":"split_clip","t":<s>}                   split without removing anything
        {"op":"set_overlay_keyframe","t":<s>,"rect":{"x":0-1,"y":0-1,"width":0-1,"height":0-1},"visible":<bool>}
                                                      move/resize/hide the camera from t onwards
        {"op":"remove_overlay_keyframe","t":<s>}
        {"op":"set_lane_gain","lane":"microphone"|"system_audio","t":<s>,"gain":0-1}
        {"op":"set_lane_muted","lane":"microphone"|"system_audio","muted":<bool>}
        {"op":"set_lane_offset","lane":"microphone"|"system_audio","seconds":<-5..5>}
                                                      nudge that lane's audio sync

        Add a "why" string to every operation: the user sees it and decides whether to apply.
        Only remove_range removes content. Never propose removing the whole recording.
        In the digest, `cameraOverlay[].rect` is [x, y, width, height] normalized to the frame.

        SESSION DIGEST (JSON):
        \(digest.compactJSON())

        REQUEST:
        \(request)
        """
    }
}
