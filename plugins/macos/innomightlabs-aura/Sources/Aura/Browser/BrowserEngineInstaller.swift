import AppKit
import Combine
import CryptoKit
import Foundation

struct BrowserEngineBundle: Equatable, Sendable {
    struct Archive: Equatable, Sendable {
        let url: URL
        let sha256: String
    }

    let nodeVersion: String
    let playwrightVersion: String
    let architecture: String
    let node: Archive
    let playwright: Archive
    var revision: String { "node-\(nodeVersion)-playwright-\(playwrightVersion)-\(architecture)" }

    static func pinned(architecture: String) -> BrowserEngineBundle {
        precondition(["arm64", "x64"].contains(architecture))
        // Node: https://nodejs.org/dist/v22.22.0/SHASUMS256.txt
        // Playwright: SHA-256 of the npm tarball, verified against dist.integrity (SHA-512).
        return BrowserEngineBundle(
            nodeVersion: "22.22.0", playwrightVersion: "1.52.0", architecture: architecture,
            node: Archive(
                url: URL(string: "https://nodejs.org/dist/v22.22.0/node-v22.22.0-darwin-\(architecture).tar.gz")!,
                sha256: architecture == "arm64"
                    ? "5ed4db0fcf1eaf84d91ad12462631d73bf4576c1377e192d222e48026a902640"
                    : "5ea50c9d6dea3dfa3abb66b2656f7a4e1c8cef23432b558d45fb538c7b5dedce"
            ),
            playwright: Archive(
                url: URL(string: "https://registry.npmjs.org/playwright-core/-/playwright-core-1.52.0.tgz")!,
                sha256: "4426ed32575cba6adf394e297a0e845eba2887dee776c4acee1d178e00f990f7"
            )
        )
    }

    static var current: BrowserEngineBundle {
        #if arch(arm64)
        pinned(architecture: "arm64")
        #else
        pinned(architecture: "x64")
        #endif
    }
}

struct BrowserEngineAcceptance: Codable, Equatable, Sendable {
    let revision: String
    let acceptedAt: Date
}

/// Call only after the explanation UI has been shown. Installing never runs npm, package scripts,
/// or a browser download; Chrome remains the user's separately installed application.
@MainActor
final class BrowserEngineInstaller: ObservableObject {
    enum State: Equatable {
        case off, awaitingConsent, installing(fraction: Double), ready
        case unavailable(String), failed(String)
    }

    @Published private(set) var state: State = .off
    let bundle: BrowserEngineBundle
    private let engineDirectory: URL
    private let defaults: UserDefaults
    private let downloader: any FileDownloading
    private let chromeApplication: @MainActor () -> URL?
    private let freeSpace: @Sendable (URL) -> Int64?
    private var installTask: Task<Void, Never>?
    private var removing = false
    private static let acceptanceKey = "Aura.browserEngineAcceptance"

    init(
        bundle: BrowserEngineBundle = .current,
        engineDirectory: URL = BrowserEngineInstaller.defaultDirectory,
        defaults: UserDefaults = .standard,
        downloader: any FileDownloading = URLSessionDownloader(),
        chromeApplication: @escaping @MainActor () -> URL? = {
            NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.google.Chrome")
        },
        freeSpace: @escaping @Sendable (URL) -> Int64? = SpeechEngineInstaller.availableBytes
    ) {
        self.bundle = bundle; self.engineDirectory = engineDirectory; self.defaults = defaults
        self.downloader = downloader; self.chromeApplication = chromeApplication; self.freeSpace = freeSpace
        refreshAvailability()
    }

    static var defaultDirectory: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Aura/Engines/browser", isDirectory: true)
    }

    var workingDirectory: URL { engineDirectory.appendingPathComponent(bundle.revision, isDirectory: true) }
    var nodeURL: URL { workingDirectory.appendingPathComponent("node/bin/node") }
    var isReady: Bool { state == .ready }
    var acceptance: BrowserEngineAcceptance? {
        defaults.data(forKey: Self.acceptanceKey).flatMap { try? JSONDecoder().decode(BrowserEngineAcceptance.self, from: $0) }
    }

    func refreshAvailability() {
        guard installTask == nil, !removing else { return }
        if chromeApplication() == nil { state = .unavailable("Install Google Chrome to record browser demos.") }
        else { state = acceptance?.revision == bundle.revision && Self.isInstalled(at: workingDirectory, bundle: bundle) ? .ready : .off }
    }

    func beginEnabling() {
        guard installTask == nil, !removing, !isReady else { return }
        guard chromeApplication() != nil else {
            state = .unavailable("Install Google Chrome to record browser demos."); return
        }
        guard freeSpace(engineDirectory).map({ $0 >= 500_000_000 }) ?? true else {
            state = .failed("The browser engine needs at least 500 MB of free disk space."); return
        }
        state = .awaitingConsent
    }

    func declineConsent() {
        guard state == .awaitingConsent else { return }
        state = .off
    }

    func acceptConsent() {
        guard state == .awaitingConsent, installTask == nil, !removing else { return }
        let record = BrowserEngineAcceptance(revision: bundle.revision, acceptedAt: Date())
        defaults.set(try? JSONEncoder().encode(record), forKey: Self.acceptanceKey)
        install()
    }

    func retry() {
        guard case .failed = state, installTask == nil, !removing else { return }
        guard acceptance?.revision == bundle.revision else { beginEnabling(); return }
        install()
    }

    func cancelInstall() { installTask?.cancel() }

    /// Wait for the worker to stop before deleting, so a late extraction cannot resurrect the engine.
    func uninstall() async throws {
        guard !removing else { return }
        removing = true
        defer { removing = false }
        installTask?.cancel()
        await installTask?.value
        do {
            if FileManager.default.fileExists(atPath: engineDirectory.path) {
                try FileManager.default.removeItem(at: engineDirectory)
            }
            defaults.removeObject(forKey: Self.acceptanceKey)
            state = .off
        } catch {
            state = .failed("The browser engine could not be removed: \(error.localizedDescription)")
            throw error
        }
    }

    private func install() {
        guard chromeApplication() != nil else {
            state = .unavailable("Install Google Chrome to record browser demos."); return
        }
        state = .installing(fraction: 0)
        let bundle = bundle, directory = workingDirectory, downloader = downloader
        let report: @Sendable (Double) -> Void = { [weak self] fraction in
            Task { @MainActor in
                guard let self, case .installing = self.state, self.installTask?.isCancelled == false else { return }
                self.state = .installing(fraction: fraction)
            }
        }
        installTask = Task { [weak self] in
            let worker = Task.detached {
                try await Self.install(bundle, at: directory, downloader: downloader, progress: report)
            }
            do {
                try await withTaskCancellationHandler { try await worker.value } onCancel: { worker.cancel() }
                try Task.checkCancellation()
                self?.state = self?.chromeApplication() == nil
                    ? .unavailable("Install Google Chrome to record browser demos.") : .ready
            } catch is CancellationError { self?.state = .off }
            catch { self?.state = .failed(error.localizedDescription) }
            self?.installTask = nil
        }
    }

    nonisolated private static func isInstalled(at directory: URL, bundle: BrowserEngineBundle) -> Bool {
        let fm = FileManager.default
        guard fm.isExecutableFile(atPath: directory.appendingPathComponent("node/bin/node").path),
              fm.fileExists(atPath: directory.appendingPathComponent("node_modules/playwright-core/index.mjs").path),
              let receipt = try? String(contentsOf: directory.appendingPathComponent(".installed"), encoding: .utf8),
              let data = try? Data(contentsOf: directory.appendingPathComponent("node_modules/playwright-core/package.json")),
              let package = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return false }
        return receipt == bundle.revision && package["name"] as? String == "playwright-core"
            && package["version"] as? String == bundle.playwrightVersion
    }

    nonisolated private static func install(
        _ bundle: BrowserEngineBundle, at directory: URL, downloader: any FileDownloading,
        progress: @escaping @Sendable (Double) -> Void
    ) async throws {
        let fm = FileManager.default, parent = directory.deletingLastPathComponent()
        let staging = parent.appendingPathComponent(".install-\(UUID().uuidString)", isDirectory: true)
        let runtime = staging.appendingPathComponent("runtime", isDirectory: true)
        try fm.createDirectory(at: runtime, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: staging) }
        let destinations = ["node", "node_modules/playwright-core"]
        for (index, archive) in [bundle.node, bundle.playwright].enumerated() {
            try Task.checkCancellation()
            let downloaded = staging.appendingPathComponent("archive.tgz")
            try await downloader.download(archive.url, to: downloaded) { _ in }
            try Task.checkCancellation()
            guard try hash(downloaded) == archive.sha256 else { throw InstallError.checksum(archive.url.lastPathComponent) }
            let destination = runtime.appendingPathComponent(destinations[index], isDirectory: true)
            try fm.createDirectory(at: destination, withIntermediateDirectories: true)
            try extract(downloaded, to: destination)
            try fm.removeItem(at: downloaded)
            progress(Double(index + 1) / 2)
        }
        try Data("{\"private\":true}".utf8).write(to: runtime.appendingPathComponent("package.json"))
        try Data(bundle.revision.utf8).write(to: runtime.appendingPathComponent(".installed"))
        guard isInstalled(at: runtime, bundle: bundle) else { throw InstallError.incomplete }
        try Task.checkCancellation()
        // Keep a previous runtime intact until every archive and the extracted layout have passed.
        let backup = staging.appendingPathComponent("previous", isDirectory: true)
        let hadPrevious = fm.fileExists(atPath: directory.path)
        if hadPrevious { try fm.moveItem(at: directory, to: backup) }
        do { try fm.moveItem(at: runtime, to: directory) }
        catch {
            if hadPrevious { try fm.moveItem(at: backup, to: directory) }
            throw error
        }
    }

    nonisolated private static func hash(_ url: URL) throws -> String {
        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        var hash = SHA256()
        while let data = try file.read(upToCount: 1_048_576), !data.isEmpty {
            try Task.checkCancellation()
            hash.update(data: data)
        }
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }

    nonisolated private static func extract(_ archive: URL, to directory: URL) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/tar")
        process.arguments = ["-xzf", archive.path, "--strip-components=1", "-C", directory.path]
        process.standardOutput = FileHandle.nullDevice; process.standardError = FileHandle.nullDevice
        try process.run()
        let deadline = Date().addingTimeInterval(120)
        while process.isRunning {
            if Task.isCancelled || Date() > deadline {
                process.terminate(); process.waitUntilExit()
                try Task.checkCancellation()
                throw InstallError.extraction
            }
            Thread.sleep(forTimeInterval: 0.02)
        }
        guard process.terminationStatus == 0 else { throw InstallError.extraction }
    }

    enum InstallError: Error, LocalizedError {
        case checksum(String), extraction, incomplete
        var errorDescription: String? {
            switch self {
            case .checksum(let file): "\(file) failed its SHA-256 check and was discarded. Try again."
            case .extraction: "The browser engine archive could not be unpacked."
            case .incomplete: "The browser engine archive has an incomplete runtime layout."
            }
        }
    }
}
