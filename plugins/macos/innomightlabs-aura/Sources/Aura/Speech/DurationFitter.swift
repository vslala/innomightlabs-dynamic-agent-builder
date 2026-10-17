import Foundation

/// Decides how new speech of one length is made to fit a selection of another.
///
/// The model is always run at its natural pace, because speech hurried to fit sounds hurried.
/// So this only ever nudges a near miss, pads a short one, and otherwise lets the speech run on
/// and asks the picture to wait for it.
struct DurationFit: Equatable, Sendable {
    enum Action: Equatable, Sendable {
        /// Speed the speech by `tempo` (above 1 is faster) so it lands exactly on the selection.
        case stretch(tempo: Double)
        /// Leave the speech alone and fill the end of the clip with quiet.
        case pad
        /// Leave the speech alone; the picture is held for the difference.
        case hold
    }

    let action: Action
    /// The finished clip's length.
    let clipDuration: TimeInterval
    /// How long the picture is held. Zero unless `action` is `.hold`.
    let hold: TimeInterval

    /// True when the hold is long enough that the user should confirm before it is made.
    var needsConfirmation: Bool { hold > DurationFitter.confirmationThreshold }
}

enum DurationFitter {
    /// Spoken length over selection length within which a time-stretch is imperceptible enough
    /// to prefer over a hold or a pad.
    static let stretchBand: ClosedRange<Double> = 0.85...1.15

    /// A picture frozen for longer than this reads as a fault, so the user is asked first.
    static let confirmationThreshold: TimeInterval = 10

    static func fit(speech: TimeInterval, selection: TimeInterval) -> DurationFit {
        guard selection > 0, speech > 0 else {
            return DurationFit(action: .pad, clipDuration: max(selection, 0), hold: 0)
        }

        let ratio = speech / selection
        if stretchBand.contains(ratio) {
            return DurationFit(action: .stretch(tempo: ratio), clipDuration: selection, hold: 0)
        }
        if ratio < stretchBand.lowerBound {
            return DurationFit(action: .pad, clipDuration: selection, hold: 0)
        }
        return DurationFit(action: .hold, clipDuration: speech, hold: speech - selection)
    }
}
