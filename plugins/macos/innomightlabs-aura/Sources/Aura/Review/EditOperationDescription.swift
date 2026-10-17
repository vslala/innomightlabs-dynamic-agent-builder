import Foundation

/// Human-readable summaries of operations, for the suggestion list and undo labels.
enum EditOperationDescription {
    static func summary(_ operation: EditOperation) -> String {
        switch operation {
        case .removeRange(let span):
            return "Remove \(TimeFormatting.timecode(span.start))–\(TimeFormatting.timecode(span.end))"
        case .removeRanges(let spans):
            let total = spans.reduce(0) { $0 + $1.duration }
            return String(
                format: "Remove %d %@ (%.1fs)",
                spans.count,
                spans.count == 1 ? "range" : "ranges",
                total
            )
        case .rename(let name):
            return name.isEmpty ? "Clear session name" : "Rename to “\(name)”"
        case .splitClip(let t):
            return "Split at \(TimeFormatting.timecode(t))"
        case .setOverlayKeyframe(let keyframe):
            return keyframe.visible
                ? "Move camera at \(TimeFormatting.timecode(keyframe.t))"
                : "Hide camera from \(TimeFormatting.timecode(keyframe.t))"
        case .removeOverlayKeyframe(let t):
            return "Remove camera keyframe at \(TimeFormatting.timecode(t))"
        case .setLaneGain(let lane, let keyframe):
            return String(
                format: "Set %@ level to %.0f%% at %@",
                name(lane), keyframe.gain * 100, TimeFormatting.timecode(keyframe.t)
            )
        case .setLaneMuted(let lane, let muted):
            return "\(muted ? "Mute" : "Unmute") \(name(lane))"
        case .setLaneStudioSound(let lane, let enabled):
            return "Studio Sound \(enabled ? "on" : "off") for \(name(lane))"
        case .setLaneOffset(let lane, let seconds):
            return String(format: "Slip %@ by %+.0fms", name(lane), seconds * 1000)
        case .excludeWords(let words):
            // Quote what is being cut: with word-level edits the times mean far less to the
            // reader than the words themselves.
            return "Cut \(words.count) word\(words.count == 1 ? "" : "s"): \(quoted(words.map(\.text)))"
        case .replaceSpeech(let replacement):
            let words = replacement.text.split(separator: " ")
            let preview = words.prefix(7).joined(separator: " ") + (words.count > 7 ? "…" : "")
            return "Re-speak \(TimeFormatting.timecode(replacement.span.start)) as “\(preview)”"
        case .restoreSpeech(let ids):
            return "Restore the original voice (\(ids.count) replacement\(ids.count == 1 ? "" : "s"))"
        case .setZoom(let zoom):
            return "Zoom in at \(TimeFormatting.timecode(zoom.span.start))"
        case .removeZooms(let ids):
            return "Remove \(ids.count) zoom\(ids.count == 1 ? "" : "s")"
        case .setCursorStyle(let style):
            return style.visible ? "Cursor: \(style.ripple ? "with" : "without") click ripples" : "Hide the cursor"
        case .setNarration(let line):
            let words = line.text.split(separator: " ")
            let preview = words.prefix(7).joined(separator: " ") + (words.count > 7 ? "…" : "")
            return "Narrate at \(TimeFormatting.timecode(line.at)): “\(preview)”"
        case .removeNarration(let ids):
            return "Remove \(ids.count) narration line\(ids.count == 1 ? "" : "s")"
        case .restoreWords(let ids):
            return "Restore \(ids.count) cut word\(ids.count == 1 ? "" : "s")"
        case .uncut(let ids):
            return "Restore \(ids.count) cut\(ids.count == 1 ? "" : "s")"
        case .removeSplit(let t):
            return "Remove split at \(TimeFormatting.timecode(t))"
        case .addMarker(let marker):
            let name = marker.label.isEmpty ? "marker" : "“\(marker.label)”"
            return "Add \(name) at \(TimeFormatting.timecode(marker.at))"
        case .removeMarker:
            return "Remove marker"
        case .renameMarker(_, let label):
            return "Rename marker to “\(label)”"
        case .moveMarker(_, let time):
            return "Move marker to \(TimeFormatting.timecode(time))"
        case .setScreenCrop(let rect):
                    return rect == nil ? "Show the whole screen frame" : "Crop the screen frame"
                case .setCameraStyle(let style):
            var parts = [style.shape.rawValue]
            if style.borderWidth > 0 { parts.append("border") }
            if style.shadowOpacity > 0 { parts.append("shadow") }
            return "Camera: \(parts.joined(separator: " + "))"
        }
    }

    /// The first few, so a sweep of fifty filler words stays one readable line.
    private static func quoted(_ texts: [String]) -> String {
        let shown = texts.prefix(6).map { "“\($0)”" }.joined(separator: ", ")
        return texts.count > 6 ? "\(shown) +\(texts.count - 6) more" : shown
    }

    private static func name(_ lane: AudioLane) -> String {
        switch lane {
        case .microphone: return "microphone"
        case .systemAudio: return "system audio"
        }
    }
}
