import Foundation

/// Human-readable summaries of operations, for the suggestion list and undo labels.
enum EditOperationDescription {
    static func summary(_ operation: EditOperation) -> String {
        switch operation {
        case .removeRange(let span):
            return "Remove \(TimeFormatting.timecode(span.start))–\(TimeFormatting.timecode(span.end))"
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
        case .setLaneOffset(let lane, let seconds):
            return String(format: "Slip %@ by %+.0fms", name(lane), seconds * 1000)
        }
    }

    private static func name(_ lane: AudioLane) -> String {
        switch lane {
        case .microphone: return "microphone"
        case .systemAudio: return "system audio"
        }
    }
}
