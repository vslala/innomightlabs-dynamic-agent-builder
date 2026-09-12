import Foundation

/// Renders captions as a sidecar subtitle file.
///
/// Times are **composition** times, because the file accompanies the exported video, which is
/// the edited timeline. That has two consequences worth stating: a cue that was cut is absent
/// entirely, and a cue that a cut split in two becomes two entries. Deriving from the
/// projection's composition spans gets both right without any special-casing.
///
/// Pure — `[ProjectedCue] -> String` — so it tests without a file system or an export.
enum SubtitleFile {
    enum Format: String, CaseIterable, Sendable {
        case srt
        case vtt

        var fileExtension: String { rawValue }
    }

    /// One rendered caption, after cuts have been applied.
    struct Entry: Equatable, Sendable {
        let start: TimeInterval
        let end: TimeInterval
        let text: String
    }

    /// Flattens cues into entries on the edited timeline.
    ///
    /// Sorted by start time, because a cue split by a cut contributes spans that interleave
    /// with its neighbours' once the gap closes.
    static func entries(from cues: [ProjectedCue], minimumDuration: TimeInterval = 0.2) -> [Entry] {
        cues
            .flatMap { cue -> [Entry] in
                let text = cue.text.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !text.isEmpty else { return [] }
                return cue.composition.compactMap { span in
                    // A sliver left by a cut that clipped nearly all of a cue would flash for
                    // a frame and read as a glitch.
                    guard span.duration >= minimumDuration else { return nil }
                    return Entry(start: span.start.seconds, end: span.end.seconds, text: text)
                }
            }
            .sorted { $0.start < $1.start }
    }

    static func render(_ entries: [Entry], as format: Format) -> String {
        switch format {
        case .srt: return renderSRT(entries)
        case .vtt: return renderVTT(entries)
        }
    }

    static func render(cues: [ProjectedCue], as format: Format) -> String {
        render(entries(from: cues), as: format)
    }

    // MARK: - Formats

    private static func renderSRT(_ entries: [Entry]) -> String {
        entries.enumerated().map { index, entry in
            """
            \(index + 1)
            \(timestamp(entry.start, separator: ",")) --> \(timestamp(entry.end, separator: ","))
            \(entry.text)
            """
        }
        .joined(separator: "\n\n")
        // SRT readers are historically fussy about the trailing blank line.
        + (entries.isEmpty ? "" : "\n")
    }

    private static func renderVTT(_ entries: [Entry]) -> String {
        let body = entries.map { entry in
            """
            \(timestamp(entry.start, separator: ".")) --> \(timestamp(entry.end, separator: "."))
            \(entry.text)
            """
        }
        .joined(separator: "\n\n")

        return "WEBVTT\n\n" + body + (entries.isEmpty ? "" : "\n")
    }

    /// `HH:MM:SS,mmm` / `HH:MM:SS.mmm`.
    ///
    /// Milliseconds are floored from a rounded total rather than computed from the fractional
    /// part, so 1.9999s does not render as `00:00:01,1000`.
    static func timestamp(_ seconds: TimeInterval, separator: String) -> String {
        let clamped = max(0, seconds)
        let totalMilliseconds = Int((clamped * 1000).rounded())
        let milliseconds = totalMilliseconds % 1000
        let totalSeconds = totalMilliseconds / 1000
        return String(
            format: "%02d:%02d:%02d%@%03d",
            totalSeconds / 3600,
            (totalSeconds % 3600) / 60,
            totalSeconds % 60,
            separator,
            milliseconds
        )
    }
}
