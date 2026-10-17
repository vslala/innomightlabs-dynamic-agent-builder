import Foundation

/// Exactly which model files Aura downloads, from where, and what they must hash to.
///
/// Pinned to one revision of the publisher's repository, so what is installed is what was
/// reviewed and a later change upstream cannot reach a user's machine unseen. Moving to another
/// revision means changing this file, which also means asking for consent again.
struct SpeechModelBundle: Equatable, Sendable {
    struct File: Equatable, Sendable {
        let name: String
        let bytes: Int64
        let sha256: String
    }

    let repository: String
    let revision: String
    let files: [File]

    let licenceName: String
    let licenceURL: URL
    let modelCardURL: URL

    var totalBytes: Int64 { files.reduce(0) { $0 + $1.bytes } }

    func url(for file: File) -> URL {
        URL(string: "https://huggingface.co/\(repository)/resolve/\(revision)/\(file.name)")!
    }

    /// F5-TTS v1 Base as an MLX bundle (fp16), the model that was listened to and judged.
    ///
    /// The checksums are the publisher's own for the two large files and computed from the
    /// pinned download for the small ones.
    static let f5TTSv1Base = SpeechModelBundle(
        repository: "aufklarer/F5TTS-v1-Base-MLX-fp16",
        revision: "685e88161a2841a5f102a6f8094613ba7131e350",
        files: [
            File(name: "config.json", bytes: 1_349,
                 sha256: "f00090d8c3d7630537bca3c8b66244048258d276890824fa7eae43eb955d0752"),
            File(name: "manifest.json", bytes: 368,
                 sha256: "83d63050294ad583123d13b3963e96d7851f39a834f88f421ce7adbb174f5af8"),
            File(name: "model.safetensors", bytes: 674_238_088,
                 sha256: "56b9649afb6a1d7e011fb8f655157ae39fd41a95debb496668718e584401b2eb"),
            // Not read for anything, but the model loader refuses a bundle without it.
            File(name: "README.md", bytes: 3_909,
                 sha256: "2a8d5b26518a62644eca3d51385ad99a1607b2b01dfef6d8683d93f1d3ae8ca7"),
            File(name: "pinyin_lexicon.tsv", bytes: 814_773,
                 sha256: "960524dcd0e958ad774fd1c2aebacd28dd4fe293e8f1c0a1f95cc1535b1fd015"),
            File(name: "vocab.txt", bytes: 13_800,
                 sha256: "2a05f992e00af9b0bd3800a8d23e78d520dbd705284ed2eedb5f4bd29398fa3c"),
            File(name: "vocos.safetensors", bytes: 27_178_204,
                 sha256: "d84bd1b98cc7bec8730213f52ce732b33ee3dac97ac8900bc2ea8d42278166d5"),
            File(name: "vocos_config.yaml", bytes: 461,
                 sha256: "da9033922f969a47f0c160010226919e59f27761fd5066f3828d46de6650b0fc")
        ],
        licenceName: "Creative Commons Attribution-NonCommercial 4.0 (CC BY-NC 4.0)",
        licenceURL: URL(string: "https://creativecommons.org/licenses/by-nc/4.0/legalcode")!,
        modelCardURL: URL(string: "https://huggingface.co/aufklarer/F5TTS-v1-Base-MLX-fp16")!
    )
}
