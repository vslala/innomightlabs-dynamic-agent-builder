import XCTest
import CryptoKit
@testable import Aura

@MainActor
final class SpeechEngineInstallerTests: XCTestCase {
    private var directory: URL!
    private var defaults: UserDefaults!
    private var suite: String!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("aura-installer-\(UUID().uuidString)", isDirectory: true)
        suite = "aura-installer-tests-\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suite)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
        defaults.removePersistentDomain(forName: suite)
    }

    // MARK: - Fixtures

    private static func hash(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private let contents: [String: Data] = [
        "model.bin": Data(repeating: 7, count: 5_000),
        "vocab.txt": Data("a\nb\nc\n".utf8)
    ]

    private var bundle: SpeechModelBundle {
        SpeechModelBundle(
            repository: "someone/model",
            revision: "rev1",
            files: contents.keys.sorted().map {
                SpeechModelBundle.File(name: $0, bytes: Int64(contents[$0]!.count), sha256: Self.hash(contents[$0]!))
            },
            licenceName: "Test Licence",
            licenceURL: URL(string: "https://example.com/licence")!,
            modelCardURL: URL(string: "https://example.com/card")!
        )
    }

    /// Serves `contents` by file name, and counts what it was asked for.
    private final class FakeDownloader: FileDownloading, @unchecked Sendable {
        private let lock = NSLock()
        private var requested: [String] = []
        var contents: [String: Data]
        var corrupt: Set<String> = []
        var fail = false
        var requests: [String] { lock.withLock { requested } }

        init(contents: [String: Data]) { self.contents = contents }

        func download(_ url: URL, to destination: URL, progress: @escaping @Sendable (Int64) -> Void) async throws {
            lock.withLock { requested.append(url.lastPathComponent) }
            if fail { throw URLError(.notConnectedToInternet) }
            var data = contents[url.lastPathComponent] ?? Data()
            if corrupt.contains(url.lastPathComponent) { data[0] ^= 0xFF }
            try data.write(to: destination)
            progress(Int64(data.count))
        }
    }

    private func installer(
        downloader: FakeDownloader? = nil,
        freeSpace: @escaping @Sendable (URL) -> Int64? = { _ in 10_000_000_000 }
    ) -> (SpeechEngineInstaller, FakeDownloader) {
        let downloader = downloader ?? FakeDownloader(contents: contents)
        return (
            SpeechEngineInstaller(
                bundle: bundle, engineDirectory: directory, defaults: defaults,
                downloader: downloader, freeSpace: freeSpace
            ),
            downloader
        )
    }

    /// Waits for the install task to settle.
    private func settle(_ installer: SpeechEngineInstaller) async {
        for _ in 0..<200 {
            if case .installing = installer.state { try? await Task.sleep(for: .milliseconds(10)) } else { return }
        }
    }

    // MARK: - Consent comes first

    func testNothingIsDownloadedUntilTheLicenceIsAccepted() async {
        let (installer, downloader) = installer()
        XCTAssertEqual(installer.state, .off)

        installer.beginEnabling()
        XCTAssertEqual(installer.state, .awaitingLicence)

        try? await Task.sleep(for: .milliseconds(50))
        XCTAssertTrue(downloader.requests.isEmpty)
    }

    func testDecliningLeavesNothingBehind() {
        let (installer, _) = installer()
        installer.beginEnabling()
        installer.declineLicence()

        XCTAssertEqual(installer.state, .off)
        XCTAssertNil(installer.acceptance)
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.path))
    }

    func testAcceptingRecordsWhatWasAgreedToAndInstalls() async {
        let (installer, downloader) = installer()
        installer.beginEnabling()
        installer.acceptLicence()
        await settle(installer)

        XCTAssertEqual(installer.state, .ready)
        XCTAssertTrue(installer.isReady)
        XCTAssertEqual(installer.acceptance?.licence, "Test Licence")
        XCTAssertEqual(installer.acceptance?.revision, "rev1")
        XCTAssertEqual(downloader.requests.sorted(), ["model.bin", "vocab.txt"])
        for name in contents.keys {
            XCTAssertTrue(FileManager.default.fileExists(atPath: installer.modelDirectory.appendingPathComponent(name).path))
        }
    }

    func testTheLicenceCannotBeAcceptedWithoutBeingShown() async {
        let (installer, downloader) = installer()
        installer.acceptLicence()                     // never asked

        XCTAssertEqual(installer.state, .off)
        XCTAssertNil(installer.acceptance)
        XCTAssertTrue(downloader.requests.isEmpty)
    }

    // MARK: - Integrity

    func testAFileThatDoesNotMatchItsHashIsDiscardedAndNothingIsInstalled() async {
        let downloader = FakeDownloader(contents: contents)
        downloader.corrupt = ["model.bin"]
        let (installer, _) = installer(downloader: downloader)
        installer.beginEnabling()
        installer.acceptLicence()
        await settle(installer)

        guard case .failed(let message) = installer.state else { return XCTFail("expected failure, got \(installer.state)") }
        XCTAssertTrue(message.contains("model.bin"))
        XCTAssertFalse(FileManager.default.fileExists(atPath: installer.modelDirectory.appendingPathComponent("model.bin").path))
        XCTAssertFalse(installer.isReady)
    }

    func testANetworkFailureIsReportedAndRetryingResumesWithoutRepeatingFinishedFiles() async {
        let downloader = FakeDownloader(contents: contents)
        let (installer, _) = installer(downloader: downloader)
        installer.beginEnabling()
        installer.acceptLicence()
        await settle(installer)
        XCTAssertEqual(installer.state, .ready)

        // Fresh installer over the same folder, with one file missing.
        try? FileManager.default.removeItem(at: installer.modelDirectory.appendingPathComponent("model.bin"))
        let again = FakeDownloader(contents: contents)
        again.fail = true
        let (second, _) = self.installer(downloader: again)
        second.beginEnabling()
        second.acceptLicence()
        await settle(second)
        guard case .failed = second.state else { return XCTFail("expected failure, got \(second.state)") }

        again.fail = false
        second.retry()
        await settle(second)

        XCTAssertEqual(second.state, .ready)
        XCTAssertEqual(again.requests.filter { $0 == "vocab.txt" }.count, 0, "a finished, verified file is not fetched again")
    }

    // MARK: - Starting up and removing

    func testAnInstallFromAnEarlierLaunchIsReadyStraightAway() async {
        let (first, _) = installer()
        first.beginEnabling()
        first.acceptLicence()
        await settle(first)

        let (relaunched, downloader) = installer()
        XCTAssertEqual(relaunched.state, .ready)
        XCTAssertTrue(downloader.requests.isEmpty)
    }

    func testFilesWithoutARecordedAgreementAreNotTrusted() async {
        let (first, _) = installer()
        first.beginEnabling()
        first.acceptLicence()
        await settle(first)
        defaults.removeObject(forKey: "Aura.speechLicenceAcceptance")

        let (relaunched, _) = installer()
        XCTAssertEqual(relaunched.state, .off)
    }

    func testATruncatedFileMeansNotInstalled() async throws {
        let (first, _) = installer()
        first.beginEnabling()
        first.acceptLicence()
        await settle(first)
        try Data([1, 2, 3]).write(to: first.modelDirectory.appendingPathComponent("model.bin"))

        let (relaunched, _) = installer()
        XCTAssertEqual(relaunched.state, .off)
    }

    func testUninstallRemovesEverythingAndAsksAgainNextTime() async {
        let (installer, _) = installer()
        installer.beginEnabling()
        installer.acceptLicence()
        await settle(installer)

        installer.uninstall()

        XCTAssertEqual(installer.state, .off)
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.path))
        installer.beginEnabling()
        XCTAssertEqual(installer.state, .awaitingLicence, "the licence is shown again")
    }

    func testNotEnoughDiskSpaceIsSaidBeforeAnythingIsAsked() {
        let (installer, downloader) = installer(freeSpace: { _ in 1_000 })
        installer.beginEnabling()

        guard case .failed(let message) = installer.state else { return XCTFail("expected failure") }
        XCTAssertTrue(message.contains("free"))
        XCTAssertTrue(downloader.requests.isEmpty)
    }

    func testTheRealBundleIsPinnedAndComplete() {
        let bundle = SpeechModelBundle.f5TTSv1Base
        XCTAssertEqual(bundle.revision.count, 40, "a full commit hash, not a branch name")
        XCTAssertTrue(bundle.files.allSatisfy { $0.sha256.count == 64 })
        XCTAssertTrue(bundle.files.contains { $0.name == "model.safetensors" })
        XCTAssertTrue(bundle.url(for: bundle.files[0]).absoluteString.contains(bundle.revision))
        XCTAssertEqual(Double(bundle.totalBytes) / 1_000_000, 702, accuracy: 5)
    }
}
