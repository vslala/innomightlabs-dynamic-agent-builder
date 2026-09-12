import Foundation

/// Builds the message sent to the agent.
///
/// Pure and unit-tested, because this is where the feature is won or lost. The agent can only
/// propose sound edits if it is told the operation vocabulary exactly and shown the recording
/// in the same clock those operations use — and the whole thing has to fit inside the A2A
/// message cap alongside the user's request.
enum EditSuggestionPrompt {
    /// Size of everything that is not the digest: the instructions, the operation vocabulary,
    /// and the user's request.
    ///
    /// Measured from the template rather than declared as a constant. The vocabulary section
    /// grows every time an operation is added, and a stale hand-maintained allowance silently
    /// overflows the server's hard message cap — a rejection, not a truncation.
    static func overhead(request: String) -> Int {
        render(digestJSON: "", request: request).count
    }

    static func build(
        instruction: String,
        context: EditSuggestionContext,
        characterBudget: Int
    ) -> String {
        let request = instruction.trimmingCharacters(in: .whitespacesAndNewlines)
        let digestBudget = max(500, characterBudget - overhead(request: request))

        let digest = (context.digest ?? SessionDigest.make(
            sessionID: context.sessionID,
            duration: context.duration,
            probes: [],
            events: EventTimeline(events: []),
            document: context.document,
            transcript: context.transcript
        )).fitting(characterBudget: digestBudget)

        return render(digestJSON: digest.compactJSON(), request: request)
    }

    private static func render(digestJSON: String, request: String) -> String {
        """
        You are the editing assistant inside Aura, a screen recorder. You are given a digest of
        one recording and asked to change it. Propose changes as JSON operations.

        Reply with one or two sentences explaining what you propose, then a JSON array of
        operations in a ```json fenced block. Use an empty array when no edit is warranted, or
        when the request is unclear — ask rather than guess.

        Reason only from the digest below. It describes this recording and no other.

        TIMELINE MODEL — read this before proposing anything.
        The recording is never modified. It has a fixed length (`durationSeconds`) and every
        time in the digest, and every time you send back, is a second on **that** timeline. What
        plays back is derived: Aura removes the `cuts` and shows what is left. So a cut does not
        renumber anything — times stay valid no matter how much has already been cut, and cuts
        are reversible.

        Consequences worth internalising:
        - Never subtract removed time from a timestamp. Read times from the digest and send
          them back unchanged.
        - `rangeCuts` and `excludedWordIds` are what is currently removed; `keptSpans` is the
          same information stated the other way round, coarsely, for orientation.
        - Proposing a cut that overlaps an existing one is harmless — they merge.

        DIGEST FORMAT
        `outline` is phrase-level and covers the whole recording: {start, end, text}.
        `words` is word-level detail for the range [detailFrom, detailTo], compactly keyed:
            i = word id, s = start, e = end, t = text
        `wordsOmitted`/`outlineCuesOmitted` count what did not fit — if the words you need are
        outside [detailFrom, detailTo], ask for them with request_transcript.
        `excludedWordIds` are words already cut; they can be brought back.
        `rangeCuts[]` are span cuts: {id, start, end, origin}. `origin` says who made it —
        "user", "agent" or "filler" (word cuts are not listed here; see `excludedWordIds`).
        Any `...Omitted` count being nonzero means that list is partial — the longest or
        earliest entries only — so never conclude from a short list that nothing else is cut.
        `splits[]` are boundaries that divide the timeline without removing anything.
        `markers[]` are facts from the recording session and are NOT editable.
        `editMarkers[]` are the editor's own markers — {id, at, label} — and are editable.
        `cameraOverlay[].rect` is [x, y, width, height] normalized to the frame.

        PREFER WORD IDS. Cutting by word id is exact; cutting by timestamp is not, and a
        timestamp you compute yourself will usually be slightly wrong.

        Copy every `id` verbatim from the digest. They are opaque handles — never invent,
        abbreviate, or reformat one; an operation naming an unknown id is rejected.

        OPERATIONS — removing
        {"op":"exclude_words","words":[{"id":<i>,"start":<s>,"end":<e>,"text":"<t>"}]}
              cut these words. Copy id/start/end/text from the digest verbatim — do not
              recompute the times. Reversible.
        {"op":"remove_range","start":<s>,"end":<s>}    cut a whole span (coarse)

        OPERATIONS — restoring
        {"op":"restore_words","ids":[<i>]}             bring cut words back
        {"op":"uncut","ids":["<rangeCuts[].id>"]}      reverse span cuts

        OPERATIONS — structure
        {"op":"split_clip","t":<s>}                    split without removing anything
        {"op":"remove_split","t":<s>}                  remove a split from `splits`
        {"op":"add_marker","at":<s>,"label":"<text>"}  label a moment for the user
        {"op":"rename_marker","id":"<editMarkers[].id>","label":"<text>"}
        {"op":"move_marker","id":"<editMarkers[].id>","to":<s>}
        {"op":"remove_marker","id":"<editMarkers[].id>"}

        OPERATIONS — camera and audio
        {"op":"set_overlay_keyframe","t":<s>,"rect":{"x":0-1,"y":0-1,"width":0-1,"height":0-1},"visible":<bool>}
              move/resize/hide the camera from t onwards
        {"op":"remove_overlay_keyframe","t":<s>}
        {"op":"set_camera_style","shape":"rectangle"|"rounded"|"circle","cornerRadius":<0-1>,
         "borderWidth":<0-1>,"borderColor":[<r>,<g>,<b>],"shadowOpacity":<0-1>,"shadowRadius":<0-1>}
              cornerRadius/borderWidth/shadowRadius are fractions of the overlay's shorter
              side; cornerRadius applies to "rounded" only.
        {"op":"set_lane_gain","lane":"microphone"|"system_audio","t":<s>,"gain":0-1}
        {"op":"set_lane_muted","lane":"microphone"|"system_audio","muted":<bool>}
        {"op":"set_lane_offset","lane":"microphone"|"system_audio","seconds":<-5..5>}
              nudge that lane's audio sync

        REQUESTS (not edits — Aura answers these and you continue)
        {"op":"request_transcript","from":<s>,"to":<s>}
              get word detail for another range. Use this instead of guessing.
        {"op":"exclude_filler_words","words":["um","uh"],"from":<s>,"to":<s>}
              Aura finds every instance of those words in that range and proposes cutting
              them, so you do not have to enumerate ids. Scope it with from/to — a whole
              recording sweep usually removes something that mattered.

        Add a "why" string to every operation: the user sees it and decides whether to apply.
        Never propose removing the whole recording.

        SESSION DIGEST (JSON):
        \(digestJSON)

        REQUEST:
        \(request)
        """
    }
}
