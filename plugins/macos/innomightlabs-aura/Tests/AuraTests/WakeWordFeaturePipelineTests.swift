import XCTest
@testable import Aura

/// Returns a fixed-shape zero vector of `outputSize`, and counts how many times it was
/// called — enough to assert the pipeline's windowing *cadence* without needing real
/// CoreML inference.
private final class FakeStageModel: WakeWordStageModel {
    let outputSize: Int
    private(set) var callCount = 0

    init(outputSize: Int) {
        self.outputSize = outputSize
    }

    func predict(_ input: [Float]) throws -> [Float] {
        callCount += 1
        return [Float](repeating: 0, count: outputSize)
    }
}

final class WakeWordFeaturePipelineTests: XCTestCase {
    private func makePipeline() -> (pipeline: WakeWordFeaturePipeline, embedding: FakeStageModel, classifier: FakeStageModel) {
        // AuraTests is a hosted unit test bundle (runs inside the Aura.app process), so
        // Bundle.main is Aura.app's own bundle, which is where the real melspectrogram
        // weight files are bundled — no need to duplicate them into a test-only bundle.
        let resourcesURL = Bundle.main.resourceURL!
        let melspectrogram = try! Melspectrogram(resourcesURL: resourcesURL)
        let embedding = FakeStageModel(outputSize: 96)
        let classifier = FakeStageModel(outputSize: 1)
        let pipeline = WakeWordFeaturePipeline(melspectrogram: melspectrogram, embedding: embedding, classifier: classifier)
        return (pipeline, embedding, classifier)
    }

    private func silentChunk() -> [Float] {
        [Float](repeating: 0, count: Melspectrogram.inputChunkSize)
    }

    func testEmbeddingDoesNotFireBeforeEnoughFramesAccumulate() throws {
        let (pipeline, embedding, classifier) = makePipeline()

        // 76-frame window needs ceil(76/5) = 16 calls at 5 frames/call to first fill.
        for _ in 0..<15 {
            _ = try pipeline.process(samples: silentChunk())
        }
        XCTAssertEqual(embedding.callCount, 0, "should not have enough frames yet (75 < 76)")
        XCTAssertEqual(classifier.callCount, 0)
    }

    func testEmbeddingFiresOnceEnoughFramesAccumulate() throws {
        let (pipeline, embedding, _) = makePipeline()

        for _ in 0..<16 {
            _ = try pipeline.process(samples: silentChunk())
        }
        // 16 calls * 5 frames = 80 frames >= 76, so at least one embedding window fired.
        XCTAssertGreaterThanOrEqual(embedding.callCount, 1)
    }

    func testClassifierDoesNotFireBeforeSixteenEmbeddings() throws {
        let (pipeline, embedding, classifier) = makePipeline()

        // One embedding window (76 frames) needs 16 calls; getting to 16 embeddings
        // needs the window to slide forward 15 more times (step=8 frames each), i.e.
        // roughly 16 + 15*8/5 calls. Use a call count well short of that.
        for _ in 0..<20 {
            _ = try pipeline.process(samples: silentChunk())
        }
        XCTAssertGreaterThan(embedding.callCount, 0)
        XCTAssertEqual(classifier.callCount, 0, "should not have 16 embeddings yet")
    }

    func testClassifierEventuallyFiresAndReturnsAScore() throws {
        let (pipeline, _, classifier) = makePipeline()

        var lastScore: Float?
        for _ in 0..<80 {
            if let score = try pipeline.process(samples: silentChunk()) {
                lastScore = score
            }
        }
        XCTAssertGreaterThan(classifier.callCount, 0)
        XCTAssertNotNil(lastScore)
        XCTAssertEqual(lastScore, 0, "fake classifier always returns 0")
    }

    /// Smoke test with the *real* bundled/converted CoreML models (not fakes) — confirms
    /// they actually load and run end-to-end without crashing. Not a claim about wake-word
    /// accuracy (that's manual-verification-only, see docs/LLD-aura-phase2-voice-control.md).
    func testRealModelsLoadAndProduceAScoreWithoutCrashing() throws {
        let resourcesURL = Bundle.main.resourceURL!
        let melspectrogram = try Melspectrogram(resourcesURL: resourcesURL)
        let embedding = try CoreMLStageModel(
            modelURL: Bundle.main.url(forResource: "embedding_model", withExtension: "mlmodelc")!,
            inputName: "input",
            inputShape: [1, 76, 32, 1]
        )
        let classifier = try CoreMLStageModel(
            modelURL: Bundle.main.url(forResource: "hey_mycroft_v0.1", withExtension: "mlmodelc")!,
            inputName: "input",
            inputShape: [1, 16, 96]
        )
        let pipeline = WakeWordFeaturePipeline(melspectrogram: melspectrogram, embedding: embedding, classifier: classifier)

        var lastScore: Float?
        for _ in 0..<80 {
            if let score = try pipeline.process(samples: silentChunk()) {
                lastScore = score
            }
        }
        let score = try XCTUnwrap(lastScore)
        XCTAssertFalse(score.isNaN)
        XCTAssertTrue(score.isFinite)
    }
}
