import XCTest
import CryptoKit
@testable import Aura

@MainActor
final class BrowserEngineInstallerTests: XCTestCase {
    private var directory: URL!
    private var defaults: UserDefaults!
    private var suite: String!
    private var bundle: BrowserEngineBundle!
    private var archives: [String: Data]!

    override func setUp() async throws {
        try await MainActor.run {
            let temporary = URL(fileURLWithPath: ProcessInfo.processInfo.environment["TMPDIR"] ?? NSTemporaryDirectory(), isDirectory: true)
            directory = temporary.appendingPathComponent("aura-browser-install-\(UUID())")
            suite = "aura-browser-install-\(UUID())"
            defaults = UserDefaults(suiteName: suite)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let node = try archive(name: "node", files: ["bin/node": "#!/bin/sh\nexit 0\n"])
            let playwright = try archive(name: "package", files: ["index.mjs": "export {};", "package.json": "{\"name\":\"playwright-core\",\"version\":\"1.52.0\"}"])
            archives = ["node.tgz": node, "playwright.tgz": playwright]
            bundle = BrowserEngineBundle(nodeVersion: "test", playwrightVersion: "1.52.0", architecture: "arm64",
                                         node: .init(url: URL(string: "https://example.com/node.tgz")!, sha256: Self.hash(node)),
                                         playwright: .init(url: URL(string: "https://example.com/playwright.tgz")!, sha256: Self.hash(playwright)))
        }
    }

    override func tearDown() async throws {
        await MainActor.run {
            try? FileManager.default.removeItem(at: directory)
            defaults.removePersistentDomain(forName: suite)
        }
    }

    private static func hash(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private func archive(name: String, files: [String: String]) throws -> Data {
        let root = directory.appendingPathComponent(UUID().uuidString)
        let folder = root.appendingPathComponent(name)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        for (path, text) in files {
            let file = folder.appendingPathComponent(path)
            try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
            try Data(text.utf8).write(to: file)
            if path == "bin/node" { try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: file.path) }
        }
        let output = root.appendingPathComponent("archive.tgz")
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/tar")
        process.arguments = ["-czf", output.path, "-C", root.path, name]
        try process.run(); process.waitUntilExit()
        XCTAssertEqual(process.terminationStatus, 0)
        return try Data(contentsOf: output)
    }

    private actor Downloader: FileDownloading {
        var files: [String: Data]
        var requests: [String] = []
        var paused = false
        init(_ files: [String: Data]) { self.files = files }
        func set(_ name: String, data: Data) { files[name] = data }
        func pause() { paused = true }
        func download(_ url: URL, to destination: URL, progress: @escaping @Sendable (Int64) -> Void) async throws {
            requests.append(url.lastPathComponent)
            if paused { try await Task.sleep(for: .seconds(30)) }
            let data = files[url.lastPathComponent] ?? Data()
            try data.write(to: destination); progress(Int64(data.count))
        }
    }

    private func installer(_ downloader: Downloader, chrome: Bool = true, bytes: Int64 = 10_000_000_000) -> BrowserEngineInstaller {
        BrowserEngineInstaller(bundle: bundle, engineDirectory: directory.appendingPathComponent("engine"), defaults: defaults,
                               downloader: downloader, chromeApplication: { chrome ? URL(fileURLWithPath: "/Applications/Google Chrome.app") : nil },
                               freeSpace: { _ in bytes })
    }

    private func settle(_ installer: BrowserEngineInstaller) async {
        for _ in 0..<500 {
            if case .installing = installer.state { try? await Task.sleep(for: .milliseconds(10)) } else { return }
        }
        XCTFail("Installer did not settle")
    }

    func testNoDownloadBeforeExplicitConsentAndDeclineLeavesNoAcceptance() async {
        let downloader = Downloader(archives), installer = installer(downloader)
        installer.acceptConsent()
        installer.beginEnabling()
        XCTAssertEqual(installer.state, .awaitingConsent)
        let requests = await downloader.requests
        XCTAssertTrue(requests.isEmpty)
        XCTAssertNil(installer.acceptance)
        installer.declineConsent()
        XCTAssertEqual(installer.state, .off)
        XCTAssertNil(installer.acceptance)
    }

    func testVerifiedArchivesInstallHostCompatibleLayoutAndPersistConsent() async throws {
        let downloader = Downloader(archives), installer = installer(downloader)
        installer.beginEnabling(); installer.acceptConsent(); await settle(installer)
        XCTAssertEqual(installer.state, .ready)
        XCTAssertEqual(installer.acceptance?.revision, bundle.revision)
        XCTAssertTrue(FileManager.default.isExecutableFile(atPath: installer.nodeURL.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: installer.workingDirectory.appendingPathComponent("node_modules/playwright-core/index.mjs").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: installer.workingDirectory.appendingPathComponent("package.json").path))
        let second = self.installer(downloader)
        XCTAssertEqual(second.state, .ready)
        let requests = await downloader.requests
        XCTAssertEqual(requests, ["node.tgz", "playwright.tgz"])
        let children = try FileManager.default.contentsOfDirectory(atPath: installer.workingDirectory.deletingLastPathComponent().path)
        XCTAssertEqual(children, [bundle.revision])
    }

    func testSecondArchiveChecksumFailurePublishesNothingAndRetryWorks() async {
        let downloader = Downloader(archives), installer = installer(downloader)
        await downloader.set("playwright.tgz", data: Data("tampered".utf8))
        installer.beginEnabling(); installer.acceptConsent(); await settle(installer)
        guard case .failed(let message) = installer.state else { return XCTFail("Expected checksum failure") }
        XCTAssertTrue(message.contains("SHA-256"))
        XCTAssertFalse(FileManager.default.fileExists(atPath: installer.workingDirectory.path))
        await downloader.set("playwright.tgz", data: archives["playwright.tgz"]!)
        installer.retry(); await settle(installer)
        XCTAssertEqual(installer.state, .ready)
    }

    func testVerifiedButMalformedArchiveIsRejected() async {
        let bad = Data("not a tar archive".utf8)
        bundle = .init(nodeVersion: "bad", playwrightVersion: "1.52.0", architecture: "arm64",
                       node: .init(url: bundle.node.url, sha256: Self.hash(bad)), playwright: bundle.playwright)
        let downloader = Downloader(archives), installer = installer(downloader)
        await downloader.set("node.tgz", data: bad)
        installer.beginEnabling(); installer.acceptConsent(); await settle(installer)
        guard case .failed = installer.state else { return XCTFail("Expected extraction failure") }
        XCTAssertFalse(FileManager.default.fileExists(atPath: installer.workingDirectory.path))
    }

    func testUninstallCancelsWorkerBeforeRemovalAndForgetsConsent() async throws {
        let downloader = Downloader(archives), installer = installer(downloader)
        await downloader.pause()
        installer.beginEnabling(); installer.acceptConsent()
        for _ in 0..<100 {
            if !(await downloader.requests).isEmpty { break }
            try await Task.sleep(for: .milliseconds(10))
        }
        try await installer.uninstall()
        XCTAssertEqual(installer.state, .off)
        XCTAssertNil(installer.acceptance)
        XCTAssertFalse(FileManager.default.fileExists(atPath: installer.workingDirectory.deletingLastPathComponent().path))
        installer.beginEnabling()
        XCTAssertEqual(installer.state, .awaitingConsent)
    }

    func testCancelLeavesNoPartialRuntime() async {
        let downloader = Downloader(archives), installer = installer(downloader)
        await downloader.pause()
        installer.beginEnabling(); installer.acceptConsent(); installer.cancelInstall(); await settle(installer)
        XCTAssertEqual(installer.state, .off)
        XCTAssertFalse(FileManager.default.fileExists(atPath: installer.workingDirectory.path))
    }

    func testMissingChromeAndInsufficientSpaceNeverDownload() async {
        let downloader = Downloader(archives)
        let noChrome = installer(downloader, chrome: false)
        noChrome.beginEnabling()
        guard case .unavailable(let message) = noChrome.state else { return XCTFail("Chrome must be unavailable") }
        XCTAssertTrue(message.contains("Google Chrome"))
        let noSpace = installer(downloader, bytes: 100)
        noSpace.beginEnabling()
        guard case .failed = noSpace.state else { return XCTFail("Must fail disk check") }
        let requests = await downloader.requests
        XCTAssertTrue(requests.isEmpty)
    }

    func testMissingInstalledFileAndMissingConsentAreNotReady() async throws {
        let downloader = Downloader(archives), installer = installer(downloader)
        installer.beginEnabling(); installer.acceptConsent(); await settle(installer)
        try FileManager.default.removeItem(at: installer.nodeURL)
        XCTAssertEqual(self.installer(downloader).state, .off)
        defaults.removeObject(forKey: "Aura.browserEngineAcceptance")
        XCTAssertEqual(self.installer(downloader).state, .off)
    }

    func testRealPinsAreExactAndArchitectureSpecific() {
        let arm = BrowserEngineBundle.pinned(architecture: "arm64"), intel = BrowserEngineBundle.pinned(architecture: "x64")
        XCTAssertNotEqual(arm.node.sha256, intel.node.sha256)
        XCTAssertNotEqual(arm.revision, intel.revision)
        XCTAssertEqual(arm.playwright, intel.playwright)
        for archive in [arm.node, intel.node, arm.playwright] {
            XCTAssertEqual(archive.sha256.count, 64)
            XCTAssertEqual(archive.url.scheme, "https")
        }
    }
}
