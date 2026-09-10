import AVFoundation
import CoreMedia
import Foundation

/// Builds a composition using `AVMutableVideoCompositionLayerInstruction` rather than a
/// custom compositor.
///
/// Repeated `setTransform(_:at:)` / `setOpacity(_:at:)` calls give step keyframes, and the
/// resulting `AVVideoComposition` is accepted verbatim by both `AVPlayerItem` and
/// `AVAssetExportSession` — so the preview and the export are the same composition rather
/// than two implementations that have to be kept in agreement.
/// (`AVVideoCompositionCoreAnimationTool` would be the other way to overlay, but it raises
/// an exception when set on an `AVPlayerItem`: it is offline-render only.)
///
/// All use of the Swift-deprecated `AVMutable…` composition classes is confined to this file,
/// so there is one place to migrate when the macOS 26 `Configuration` API becomes reachable.
@MainActor
struct LayerInstructionCompositionBuilder: CompositionBuilding {
    func build(_ timeline: ResolvedTimeline, maxRenderDimension: CGFloat?) async throws -> BuiltComposition {
        let composition = AVMutableComposition()

        var base: InsertedVideoLayer?
        if let layer = timeline.base {
            base = await insertVideo(layer, into: composition, timeline: timeline)
        }
        var overlay: InsertedVideoLayer?
        if let layer = timeline.overlay {
            overlay = await insertVideo(layer, into: composition, timeline: timeline)
        }
        var audio: [InsertedAudioLane] = []
        for lane in timeline.audio {
            if let inserted = await insertAudio(lane, into: composition, timeline: timeline) {
                audio.append(inserted)
            }
        }

        guard base != nil || overlay != nil || !audio.isEmpty else {
            throw CompositionError.noUsableMedia
        }

        let renderSize = PiPGeometry.renderSize(timeline.renderSize, maxDimension: maxRenderDimension)
        let videoComposition = makeVideoComposition(
            timeline: timeline,
            renderSize: renderSize,
            layers: [overlay, base].compactMap { $0 } // front-to-back: the PiP goes on top
        )
        let audioMix = makeAudioMix(lanes: audio)

        // A snapshot, so nothing that happens to the mutable composition afterwards can
        // affect an export already in flight.
        let snapshot = composition.copy() as? AVComposition ?? composition

        #if DEBUG
        await Self.assertValid(videoComposition, snapshot: snapshot, duration: composition.duration)
        #endif

        return BuiltComposition(
            asset: snapshot,
            videoComposition: videoComposition,
            audioMix: audioMix,
            duration: composition.duration,
            renderSize: renderSize
        )
    }

    // MARK: - Tracks

    private struct InsertedVideoLayer {
        let layer: ResolvedVideoLayer
        let trackID: CMPersistentTrackID
        /// The ranges the composition track actually holds samples for. A list rather than
        /// a single span because the pieces can be disjoint — an interior insert can fail,
        /// and clips need not be in ascending source order — and a union would paper over
        /// the holes, which is exactly what this bookkeeping exists to prevent.
        let covered: [CMTimeRange]

        func covers(_ timeRange: CMTimeRange) -> Bool {
            covered.contains { $0.intersection(timeRange).duration > .zero }
        }
    }

    private struct InsertedAudioLane {
        let lane: ResolvedAudioLane
        let trackID: CMPersistentTrackID
    }

    private func insertVideo(
        _ layer: ResolvedVideoLayer,
        into composition: AVMutableComposition,
        timeline: ResolvedTimeline
    ) async -> InsertedVideoLayer? {
        guard let track = composition.addMutableTrack(
            withMediaType: .video,
            preferredTrackID: kCMPersistentTrackID_Invalid
        ) else { return nil }

        // Geometry has exactly one owner — the layer instruction's transform. `insertTimeRange`
        // does not carry `preferredTransform` onto the composition track, so relying on it
        // here would be a second, silent source of truth.
        track.preferredTransform = .identity

        guard let covered = await insertClips(of: layer.probe, into: track, timeline: timeline) else {
            // Never leave an unpopulated track behind: it still gets a track ID and a zero
            // naturalSize, and a layer instruction naming it invalidates the composition.
            composition.removeTrack(track)
            return nil
        }

        return InsertedVideoLayer(layer: layer, trackID: track.trackID, covered: covered)
    }

    private func insertAudio(
        _ lane: ResolvedAudioLane,
        into composition: AVMutableComposition,
        timeline: ResolvedTimeline
    ) async -> InsertedAudioLane? {
        guard let track = composition.addMutableTrack(
            withMediaType: .audio,
            preferredTrackID: kCMPersistentTrackID_Invalid
        ) else { return nil }

        guard await insertClips(of: lane.probe, into: track, timeline: timeline) != nil else {
            composition.removeTrack(track)
            return nil
        }

        return InsertedAudioLane(lane: lane, trackID: track.trackID)
    }

    /// Lays the edit decision list down on one composition track.
    ///
    /// Source ranges are intersected with what the file actually contains first: the four
    /// recorded files share a time origin but not a duration, so a clip can legitimately
    /// extend past the end of one of them. The leading empty edit each file carries from
    /// `startSession(atSourceTime:)` is what keeps their origins aligned, so source time is
    /// used directly rather than being re-aligned here.
    private func insertClips(
        of probe: SourceTrackProbe,
        into track: AVMutableCompositionTrack,
        timeline: ResolvedTimeline
    ) async -> [CMTimeRange]? {
        let asset = AVURLAsset(
            url: probe.url,
            options: [AVURLAssetPreferPreciseDurationAndTimingKey: true]
        )
        guard
            let source = try? await asset.loadTracks(withMediaType: probe.kind.mediaType).first
        else { return nil }

        let available = CMTimeRange(start: .zero, duration: probe.duration)
        var covered: [CMTimeRange] = []

        for segment in timeline.timeMap.segments {
            let usable = segment.source.intersection(available)
            guard usable.duration > .zero else { continue }

            let at = segment.composition.start + (usable.start - segment.source.start)
            do {
                try track.insertTimeRange(usable, of: source, at: at)
                covered.append(CMTimeRange(start: at, duration: usable.duration))
            } catch {
                continue
            }
        }

        return covered.isEmpty ? nil : covered
    }

    // MARK: - Video composition

    private func makeVideoComposition(
        timeline: ResolvedTimeline,
        renderSize: CGSize,
        layers: [InsertedVideoLayer]
    ) -> AVVideoComposition? {
        guard !layers.isEmpty, timeline.duration > .zero else { return nil }

        let videoComposition = AVMutableVideoComposition()
        // Both must be non-zero: assigning a composition with a zero renderSize or
        // frameDuration to an AVPlayerItem raises an uncatchable ObjC exception.
        videoComposition.renderSize = renderSize
        videoComposition.frameDuration = timeline.frameDuration
        // Left at the default invalid track ID on purpose. Deriving frame timing from the
        // screen track looks right for a variable-rate source and is wrong: a static screen
        // produces one sample with a very long duration, so the compositor would emit a
        // single composed frame across that span and freeze the camera overlay with it.
        videoComposition.sourceTrackIDForFrameTiming = kCMPersistentTrackID_Invalid

        if let tags = Self.colorTags(for: timeline) {
            videoComposition.colorPrimaries = tags.primaries
            videoComposition.colorTransferFunction = tags.transfer
            videoComposition.colorYCbCrMatrix = tags.matrix
        }

        videoComposition.instructions = Self.boundaries(timeline: timeline, layers: layers)
            .adjacentPairs()
            .compactMap { start, end in
                let timeRange = CMTimeRange(start: start, end: end)
                guard timeRange.duration > .zero else { return nil }
                return Self.instruction(
                    timeRange: timeRange,
                    layers: layers,
                    timeline: timeline,
                    renderSize: renderSize
                )
            }

        return videoComposition.copy() as? AVVideoComposition ?? videoComposition
    }

    /// Instructions have to tile `[0, duration]` with no gaps or overlaps.
    ///
    /// Boundaries are the union of every keyframe time and the start/end of what each video
    /// track actually covers. Cutting at track boundaries means the stretch after a source
    /// file ended early renders as clean background instead of holding a stale final frame;
    /// cutting at every keyframe time means each instruction has a single constant overlay
    /// state, so transforms are set once per instruction and ramps — whose overlapping is an
    /// exception — never come into it.
    private static func boundaries(
        timeline: ResolvedTimeline,
        layers: [InsertedVideoLayer]
    ) -> [CMTime] {
        var times: Set<CMTime> = [.zero, timeline.duration]

        for layer in layers {
            for range in layer.covered {
                times.insert(range.start)
                times.insert(range.end)
            }
            for keyframe in layer.layer.keyframes {
                times.insert(keyframe.at)
            }
        }

        return times
            .filter { $0.isNumeric && $0 >= .zero && $0 <= timeline.duration }
            .sorted()
    }

    private static func instruction(
        timeRange: CMTimeRange,
        layers: [InsertedVideoLayer],
        timeline: ResolvedTimeline,
        renderSize: CGSize
    ) -> AVMutableVideoCompositionInstruction {
        let instruction = AVMutableVideoCompositionInstruction()
        instruction.timeRange = timeRange
        instruction.backgroundColor = CGColor(red: 0, green: 0, blue: 0, alpha: 1)

        instruction.layerInstructions = layers.compactMap { inserted -> AVVideoCompositionLayerInstruction? in
            // Only include a layer that has content here, so an early-ending track — or a
            // hole between two inserted pieces — does not leave an instruction pointing at
            // nothing, which would hold a stale final frame.
            guard inserted.covers(timeRange) else { return nil }

            let state = Self.state(of: inserted.layer, at: timeRange.start)
            let layerInstruction = AVMutableVideoCompositionLayerInstruction()
            layerInstruction.trackID = inserted.trackID

            let destination = state.rect.scaled(to: renderSize)
            let transform = PiPGeometry.transform(
                displaySize: inserted.layer.probe.displaySize ?? renderSize,
                preferredTransform: inserted.layer.probe.preferredTransform,
                destination: destination
            )

            // Always both, always at the instruction's own start. Before the first time a
            // transform is set it is held at the identity and opacity at 1.0 — which would
            // render the camera at native size in the top-left, covering the screen.
            layerInstruction.setTransform(transform, at: timeRange.start)
            layerInstruction.setOpacity(state.visible ? 1 : 0, at: timeRange.start)
            return layerInstruction
        }

        return instruction
    }

    /// The step-keyframe lookup: the last keyframe at or before `time`, falling back to the
    /// first so there is always an answer.
    private static func state(of layer: ResolvedVideoLayer, at time: CMTime) -> ResolvedOverlayKeyframe {
        layer.keyframes.last { $0.at <= time }
            ?? layer.keyframes.first
            ?? ResolvedOverlayKeyframe(
                at: .zero,
                rect: NormalizedRect(x: 0, y: 0, width: 1, height: 1),
                visible: true
            )
    }

    /// Taken from the base layer — it is the layer carrying text, so it is the one whose
    /// colour must not shift.
    private static func colorTags(for timeline: ResolvedTimeline) -> (primaries: String, transfer: String, matrix: String)? {
        guard
            let probe = timeline.base?.probe,
            let primaries = probe.colorPrimaries,
            let transfer = probe.colorTransferFunction,
            let matrix = probe.colorYCbCrMatrix
        else { return nil }
        return (primaries, transfer, matrix)
    }

    // MARK: - Audio

    private func makeAudioMix(lanes: [InsertedAudioLane]) -> AVAudioMix? {
        guard !lanes.isEmpty else { return nil }

        let mix = AVMutableAudioMix()
        mix.inputParameters = lanes.map { inserted in
            let parameters = AVMutableAudioMixInputParameters()
            parameters.trackID = inserted.trackID
            for keyframe in inserted.lane.keyframes {
                parameters.setVolume(Float(keyframe.gain), at: keyframe.at)
            }
            return parameters
        }

        return mix.copy() as? AVAudioMix ?? mix
    }

    #if DEBUG
    /// Catches an invalid composition here, where it is an assertion, rather than downstream
    /// where AVFoundation would raise an uncatchable ObjC exception and kill the process.
    private static func assertValid(
        _ videoComposition: AVVideoComposition?,
        snapshot: AVAsset,
        duration: CMTime
    ) async {
        guard let videoComposition, duration > .zero else { return }
        guard
            let tracks = try? await snapshot.loadTracks(withMediaType: .video),
            !tracks.isEmpty
        else { return }

        let valid = videoComposition.isValid(
            for: tracks,
            assetDuration: duration,
            timeRange: CMTimeRange(start: .zero, duration: duration),
            validationDelegate: nil
        )
        assert(valid, "Video composition failed validation — it would raise an ObjC exception downstream")
    }
    #endif
}

private extension Array {
    /// `[a, b, c]` -> `[(a, b), (b, c)]`
    func adjacentPairs() -> [(Element, Element)] {
        guard count > 1 else { return [] }
        return (0..<(count - 1)).map { (self[$0], self[$0 + 1]) }
    }
}
