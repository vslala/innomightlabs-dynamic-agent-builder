import Foundation

enum SpeechEngineError: Error, LocalizedError {
    case notEnabled
    case unavailable(String)

    var errorDescription: String? {
        switch self {
        case .notEnabled: return "Turn on Speech Replacement in Settings first."
        case .unavailable(let reason): return reason
        }
    }
}

/// What review windows ask for a voice: the installer, and the one engine built from what it
/// installed.
///
/// App-wide rather than per window, because the loaded model holds about 2.5 GB and two review
/// windows must not each load their own.
@MainActor
final class SpeechEngineHub: ObservableObject {
    let installer: SpeechEngineInstaller
    private let makeEngine: @MainActor (URL) -> any SpeechSynthesizing
    private var engine: (any SpeechSynthesizing)?
    private var engineDirectory: URL?

    init(
        installer: SpeechEngineInstaller = SpeechEngineInstaller(),
        makeEngine: @escaping @MainActor (URL) -> any SpeechSynthesizing = { F5SpeechEngine(bundleDirectory: $0) }
    ) {
        self.installer = installer
        self.makeEngine = makeEngine
    }

    var isReady: Bool { installer.isReady }

    func synthesizer() throws -> any SpeechSynthesizing {
        guard installer.isReady else { throw SpeechEngineError.notEnabled }

        // Rebuilt if the installed model moved (uninstalled and installed again), never reused
        // across that.
        if let engine, engineDirectory == installer.modelDirectory { return engine }
        let created = makeEngine(installer.modelDirectory)
        engine = created
        engineDirectory = installer.modelDirectory
        return created
    }

    func uninstall() {
        engine = nil
        engineDirectory = nil
        installer.uninstall()
    }
}
