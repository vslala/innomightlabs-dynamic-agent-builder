import Foundation

/// Buffers melspectrogram frames into the sliding windows the embedding and classifier
/// stages expect, and runs them as soon as enough frames have accumulated.
///
/// Verified (from openWakeWord's own source): a 76-melspec-frame window feeds the
/// embedding model, stepped by 8 frames each time enough new frames arrive; the last 16
/// resulting 96-dim embeddings feed the classifier. `melspectrogram` produces 5 frames
/// per 80ms/1280-sample call (not 32, as an earlier secondhand read of the docs assumed)
/// — this class doesn't hard-code that rate, it just accumulates however many arrive.
final class WakeWordFeaturePipeline {
    private static let embeddingWindowSize = 76
    private static let embeddingStepSize = 8
    private static let classifierWindowSize = 16
    private static let melBins = Melspectrogram.melBins
    private static let embeddingDimension = 96

    private let melspectrogram: Melspectrogram
    private let embedding: WakeWordStageModel
    private let classifier: WakeWordStageModel

    private var melspecFrameBuffer: [[Float]] = []
    private var embeddingBuffer: [[Float]] = []

    init(melspectrogram: Melspectrogram, embedding: WakeWordStageModel, classifier: WakeWordStageModel) {
        self.melspectrogram = melspectrogram
        self.embedding = embedding
        self.classifier = classifier
    }

    /// Feed 1280 raw (int16-range) float32 samples (80ms @ 16kHz). Returns the latest
    /// classifier score if a full classifier window was completed during this call,
    /// else `nil`. May run the embedding/classifier stages more than once per call if
    /// enough melspec frames have accumulated to complete multiple sliding-window steps.
    func process(samples: [Float]) throws -> Float? {
        let (frameCount, values) = melspectrogram.process(samples: samples)
        for frame in 0..<frameCount {
            let start = frame * Self.melBins
            melspecFrameBuffer.append(Array(values[start..<(start + Self.melBins)]))
        }

        var latestScore: Float?

        while melspecFrameBuffer.count >= Self.embeddingWindowSize {
            let window = melspecFrameBuffer.prefix(Self.embeddingWindowSize).flatMap { $0 }
            let embeddingOutput = try embedding.predict(Array(window))
            embeddingBuffer.append(embeddingOutput)
            if embeddingBuffer.count > Self.classifierWindowSize {
                embeddingBuffer.removeFirst(embeddingBuffer.count - Self.classifierWindowSize)
            }

            melspecFrameBuffer.removeFirst(Self.embeddingStepSize)

            if embeddingBuffer.count == Self.classifierWindowSize {
                let classifierInput = embeddingBuffer.flatMap { $0 }
                let score = try classifier.predict(classifierInput)
                latestScore = score.first
            }
        }

        return latestScore
    }
}
