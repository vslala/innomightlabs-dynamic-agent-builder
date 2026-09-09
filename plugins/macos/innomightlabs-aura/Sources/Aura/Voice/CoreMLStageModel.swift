import CoreML
import Foundation

enum VoiceError: Error, LocalizedError {
    case modelLoadFailed(String)

    var errorDescription: String? {
        switch self {
        case .modelLoadFailed(let reason):
            return reason
        }
    }
}

/// A single CoreML-backed stage in the wake-word pipeline: one flat row-major float
/// input in, one flat row-major float output out. Abstracted so
/// `WakeWordFeaturePipeline`'s buffering/windowing logic is unit-testable against a
/// fake, without loading real models.
protocol WakeWordStageModel {
    func predict(_ input: [Float]) throws -> [Float]
}

final class CoreMLStageModel: WakeWordStageModel {
    private let model: MLModel
    private let inputName: String
    private let inputShape: [NSNumber]
    private let outputName: String

    init(modelURL: URL, inputName: String, inputShape: [Int]) throws {
        model = try MLModel(contentsOf: modelURL)
        self.inputName = inputName
        self.inputShape = inputShape.map { NSNumber(value: $0) }
        guard let outputName = model.modelDescription.outputDescriptionsByName.keys.first else {
            throw VoiceError.modelLoadFailed("\(modelURL.lastPathComponent) has no outputs")
        }
        self.outputName = outputName
    }

    func predict(_ input: [Float]) throws -> [Float] {
        let array = try MLMultiArray(shape: inputShape, dataType: .float32)
        for (index, value) in input.enumerated() {
            array[index] = NSNumber(value: value)
        }

        let provider = try MLDictionaryFeatureProvider(dictionary: [inputName: MLFeatureValue(multiArray: array)])
        let result = try model.prediction(from: provider)
        guard let output = result.featureValue(for: outputName)?.multiArrayValue else {
            throw VoiceError.modelLoadFailed("output \"\(outputName)\" missing or not a multi-array")
        }

        var flat = [Float](repeating: 0, count: output.count)
        for index in 0..<output.count {
            flat[index] = output[index].floatValue
        }
        return flat
    }
}
