import CryptoKit
import Foundation

/// What the user agreed to, and when. Stored so a changed model asks again.
struct SpeechLicenceAcceptance: Codable, Equatable, Sendable {
    let licence: String
    let revision: String
    let acceptedAt: Date
}

/// Turns Speech Replacement on: shows what the licence allows, downloads the model after the
/// user agrees, checks every file, and removes it all again on request.
///
/// Nothing is bundled with Aura and nothing downloads until `acceptLicence()`. Downloads go
/// straight to the publisher, are checked against hashes pinned in `SpeechModelBundle`, and are
/// moved into place only once they match, so a half-finished or tampered file is never loaded.
@MainActor
final class SpeechEngineInstaller: ObservableObject {
    enum State: Equatable {
        case off
        /// The licence is on screen waiting for a decision. Nothing has been downloaded.
        case awaitingLicence
        case installing(fraction: Double)
        case ready
        case failed(String)
    }

    @Published private(set) var state: State

    let bundle: SpeechModelBundle

    private let engineDirectory: URL
    private let defaults: UserDefaults
    private let downloader: any FileDownloading
    private let freeSpace: @Sendable (URL) -> Int64?
    private var installTask: Task<Void, Never>?

    private static let acceptanceKey = "Aura.speechLicenceAcceptance"
    /// Room left over after the model, so the install cannot fill the disk to the brim.
    private static let spaceMargin: Int64 = 300_000_000

    init(
        bundle: SpeechModelBundle = .f5TTSv1Base,
        engineDirectory: URL = SpeechEngineInstaller.defaultDirectory,
        defaults: UserDefaults = .standard,
        downloader: any FileDownloading = URLSessionDownloader(),
        freeSpace: @escaping @Sendable (URL) -> Int64? = SpeechEngineInstaller.availableBytes
    ) {
        self.bundle = bundle
        self.engineDirectory = engineDirectory
        self.defaults = defaults
        self.downloader = downloader
        self.freeSpace = freeSpace
        state = .off
        if isInstalled && acceptance?.revision == bundle.revision { state = .ready }
    }

    static var defaultDirectory: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Aura/Engines/f5tts", isDirectory: true)
    }

    nonisolated static func availableBytes(at url: URL) -> Int64? {
        var directory = url
        // The folder may not exist yet; ask about the nearest one that does.
        while !FileManager.default.fileExists(atPath: directory.path), directory.pathComponents.count > 1 {
            directory.deleteLastPathComponent()
        }
        return (try? directory.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey]))?
            .volumeAvailableCapacityForImportantUsage
    }

    // MARK: - What is installed

    /// Where the model files live. Per revision, so a newer bundle never mixes with an older one.
    var modelDirectory: URL {
        engineDirectory.appendingPathComponent(bundle.revision, isDirectory: true)
    }

    var isReady: Bool { state == .ready }

    var acceptance: SpeechLicenceAcceptance? {
        defaults.data(forKey: Self.acceptanceKey).flatMap { try? JSONDecoder().decode(SpeechLicenceAcceptance.self, from: $0) }
    }

    /// Cheap enough to run at launch: sizes, not hashes. Hashes were checked when each file was
    /// moved into place, and a file only gets into place by passing them.
    private var isInstalled: Bool {
        bundle.files.allSatisfy { file in
            let attributes = try? FileManager.default.attributesOfItem(atPath: modelDirectory.appendingPathComponent(file.name).path)
            return (attributes?[.size] as? NSNumber)?.int64Value == file.bytes
        }
    }

    // MARK: - Turning it on

    /// Starts enabling: checks there is room, then shows the licence.
    func beginEnabling() {
        guard state == .off || isFailed else { return }

        if let free = freeSpace(engineDirectory), free < bundle.totalBytes + Self.spaceMargin {
            state = .failed(String(
                format: "Speech Replacement needs about %.0f MB free, and this Mac has %.0f MB.",
                Double(bundle.totalBytes + Self.spaceMargin) / 1_000_000, Double(free) / 1_000_000
            ))
            return
        }
        state = .awaitingLicence
    }

    func declineLicence() {
        guard state == .awaitingLicence else { return }
        state = .off
    }

    /// The user agreed: record it, then download and verify.
    func acceptLicence() {
        guard state == .awaitingLicence else { return }

        let record = SpeechLicenceAcceptance(licence: bundle.licenceName, revision: bundle.revision, acceptedAt: Date())
        defaults.set(try? JSONEncoder().encode(record), forKey: Self.acceptanceKey)
        install()
    }

    func retry() {
        guard isFailed, acceptance?.revision == bundle.revision else { return beginEnabling() }
        install()
    }

    func cancelInstall() {
        installTask?.cancel()
    }

    func uninstall() {
        installTask?.cancel()
        try? FileManager.default.removeItem(at: engineDirectory)
        state = .off
    }

    private var isFailed: Bool {
        if case .failed = state { return true }
        return false
    }

    // MARK: - Installing

    private func install() {
        state = .installing(fraction: 0)
        let bundle = bundle, directory = modelDirectory, downloader = downloader
        let report: @Sendable (Double) -> Void = { [weak self] fraction in
            Task { @MainActor in self?.report(fraction) }
        }

        installTask = Task { [weak self] in
            do {
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                var finished: Int64 = 0

                for file in bundle.files {
                    try Task.checkCancellation()
                    let final = directory.appendingPathComponent(file.name)

                    if await Self.verifies(final, file) {
                        finished += file.bytes      // downloaded and checked on an earlier attempt
                    } else {
                        let partial = directory.appendingPathComponent(file.name + ".part")
                        defer { try? FileManager.default.removeItem(at: partial) }
                        let alreadyDone = finished

                        try await downloader.download(bundle.url(for: file), to: partial) { received in
                            report(Double(alreadyDone + received) / Double(bundle.totalBytes))
                        }
                        guard await Self.verifies(partial, file) else { throw InstallError.checksumMismatch(file.name) }
                        try? FileManager.default.removeItem(at: final)
                        try FileManager.default.moveItem(at: partial, to: final)
                        finished += file.bytes
                    }
                }
                self?.finishInstalling()
            } catch is CancellationError {
                self?.state = .off
            } catch {
                self?.state = .failed(error.localizedDescription)
            }
            self?.installTask = nil
        }
    }

    private func report(_ fraction: Double) {
        guard case .installing = state else { return }
        state = .installing(fraction: min(1, max(0, fraction)))
    }

    private func finishInstalling() {
        state = isInstalled ? .ready : .failed("The model files are incomplete.")
    }

    /// Size first, which settles nearly every mismatch without reading the file; then the hash.
    ///
    /// `async` on purpose: a nonisolated async function runs off the main actor, and hashing a
    /// 670 MB file there would freeze the window it is reporting progress in.
    nonisolated private static func verifies(_ url: URL, _ file: SpeechModelBundle.File) async -> Bool {
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
              (attributes[.size] as? NSNumber)?.int64Value == file.bytes,
              let digest = sha256(of: url)
        else { return false }
        return digest == file.sha256
    }

    nonisolated static func sha256(of url: URL) -> String? {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return nil }
        defer { try? handle.close() }

        var hasher = SHA256()
        while let chunk = try? handle.read(upToCount: 4 * 1_024 * 1_024), !chunk.isEmpty {
            hasher.update(data: chunk)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    enum InstallError: Error, LocalizedError {
        case checksumMismatch(String)

        var errorDescription: String? {
            switch self {
            case .checksumMismatch(let name):
                return "\(name) did not match the publisher's checksum, so it was discarded. Try again."
            }
        }
    }
}
