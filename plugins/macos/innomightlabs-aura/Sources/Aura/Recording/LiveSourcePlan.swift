import Foundation

/// What a live profile change does to a running source list.
///
/// Sources are matched by the set of kinds they own, which is their identity: one `SCStream`
/// produces screen and system audio together, so switching system audio off changes that
/// source's identity and it is rebuilt rather than reconfigured. A source whose identity is
/// unchanged is retained untouched — the camera and microphone files must not be interrupted
/// by a change that has nothing to do with them.
struct LiveSourcePlan {
    let retained: [any CaptureSource]
    let removed: [any CaptureSource]
    let added: [any CaptureSource]

    var isEmpty: Bool { removed.isEmpty && added.isEmpty }

    /// The source list once this plan has been applied, in the order `CaptureSourceFactory`
    /// would produce for the desired request had it produced these instances.
    var resulting: [any CaptureSource] { retained + added }

    /// Diffs `desired` against `live` by kind-set identity.
    ///
    /// Pure, and the only place the reconciliation itself is decided — no branch per source and
    /// none per direction. `CaptureSourceFactory.plan(live:for:)` supplies `desired` from a
    /// `RecordingRequest`; kept separate so the diff itself is testable without a real screen
    /// target, which nothing outside a live device lookup can construct.
    static func reconciling(live: [any CaptureSource], desired: [any CaptureSource]) -> LiveSourcePlan {
        let liveKeys = Set(live.map(\.kindKey))
        let desiredKeys = Set(desired.map(\.kindKey))

        return LiveSourcePlan(
            retained: live.filter { desiredKeys.contains($0.kindKey) },
            removed: live.filter { !desiredKeys.contains($0.kindKey) },
            added: desired.filter { !liveKeys.contains($0.kindKey) }
        )
    }
}

extension CaptureSource {
    /// This source's reconciliation identity.
    var kindKey: Set<TrackKind> { Set(kinds) }
}

extension CaptureSourceFactory {
    /// Diffs the sources `request` calls for against what is currently running.
    ///
    /// Reusing `sources(for:)` for the desired side is what keeps "which sources a profile
    /// needs" answered in exactly one place — the factory is never asked the question twice.
    static func plan(live: [any CaptureSource], for request: RecordingRequest) -> LiveSourcePlan {
        .reconciling(live: live, desired: sources(for: request))
    }
}
