import Foundation

/// How an audio amplitude maps to a fraction of the lane's half-height.
///
/// Linear is the textbook waveform and is useless for speech. Measured on a real recording:
/// peak 0.35 (-9 dBFS) but a median 10ms bucket of 0.0022, which at linear full scale is
/// 0.22% of half-height — sub-pixel, so the lane draws as a flat line with occasional
/// flecks. The dynamic range of speech is simply too wide for a linear axis.
///
/// Decibel is therefore the default, as it is in Audacity's "Waveform (dB)" view: it spends
/// the lane's height on the range speech actually occupies. With a -60 dB floor that same
/// median bucket becomes 12% of half-height and the peaks reach 85%.
enum WaveformScale: String, CaseIterable, Sendable {
    case decibel
    case linear

    /// Anything quieter than this is floor. -60 dBFS is below the noise floor of a normal
    /// room recording, so genuine silence still reads as silence.
    static let decibelFloor: Double = -60

    var label: String {
        switch self {
        case .decibel: return "dB"
        case .linear: return "Linear"
        }
    }

    /// Maps a signed sample value to a signed fraction of half-height, in `-1...1`.
    ///
    /// Sign is preserved so the envelope still straddles the centre line; only the magnitude
    /// is rescaled.
    func fraction(_ amplitude: Float) -> Double {
        let value = Double(amplitude)
        guard value.isFinite, value != 0 else { return 0 }

        let magnitude = min(1, abs(value))
        let scaled: Double
        switch self {
        case .linear:
            scaled = magnitude
        case .decibel:
            let decibels = 20 * log10(magnitude)
            scaled = max(0, (decibels - Self.decibelFloor) / -Self.decibelFloor)
        }
        return value < 0 ? -scaled : scaled
    }
}
