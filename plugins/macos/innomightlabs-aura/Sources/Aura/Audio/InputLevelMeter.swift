import Foundation

/// Pure. Turns an RMS sample into dBFS, then into a 0...1 bar with asymmetric smoothing: fast
/// attack so a transient is visible, slow decay so the bar is readable rather than flickering.
struct InputLevelMeter: Equatable, Sendable {
    static let floor: Double = -60

    var attack: Double = 0.5
    var decay: Double = 0.12

    /// Floored rather than propagating silence, negative-infinity or a NaN input as -infinity
    /// or NaN — nothing downstream should ever see a non-finite level.
    func dbFS(rms: Double) -> Double {
        guard rms.isFinite, rms > 0 else { return Self.floor }
        let db = 20 * log10(rms)
        return db.isFinite ? max(Self.floor, db) : Self.floor
    }

    /// `floor...0` mapped to `0...1`. A non-finite input reads as silence rather than
    /// propagating.
    func normalized(dbFS: Double) -> Double {
        guard dbFS.isFinite else { return 0 }
        let clamped = max(Self.floor, min(0, dbFS))
        return (clamped - Self.floor) / (0 - Self.floor)
    }

    /// One-pole smoothing: whichever rate applies moves `previous` a fraction of the way to
    /// `next` per call, so a rising input (attack) reaches its target faster than a falling
    /// one (decay).
    func smoothed(previous: Double, next: Double) -> Double {
        let rate = next > previous ? attack : decay
        return previous + (next - previous) * rate
    }
}
