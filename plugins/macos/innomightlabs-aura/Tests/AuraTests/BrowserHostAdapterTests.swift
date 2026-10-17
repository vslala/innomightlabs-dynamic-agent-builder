import XCTest
import Darwin
@testable import Aura

final class BrowserHostAdapterTests: XCTestCase {
    private struct Fixture: Sendable {
        let directory: URL
        let host: PlaywrightBrowserHost
        var configuration: BrowserLaunch {
            BrowserLaunch(profileDirectory: directory.appendingPathComponent("profile"),
                          startURL: URL(string: "https://example.com")!, window: .init(width: 1440, height: 900),
                          allowedOrigins: ["https://example.com"])
        }
    }

    private func fixture(mode: String = "normal") throws -> Fixture {
        guard let node = ["/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node"]
            .first(where: { FileManager.default.isExecutableFile(atPath: $0) }) else { throw XCTSkip("Node is not installed") }
        let temporary = ProcessInfo.processInfo.environment["TMPDIR"].map { URL(fileURLWithPath: $0) } ?? FileManager.default.temporaryDirectory
        let directory = temporary.appendingPathComponent("browser-host-tests-\(UUID())")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let script = directory.appendingPathComponent("fake.mjs")
        let source = """
        import { createInterface } from 'node:readline';
        import { spawn } from 'node:child_process';
        import { writeFileSync } from 'node:fs';
        const mode = '\(mode)';
        const viewport = {width: 1280, height: 720, devicePixelRatio: 2};
        const send = value => process.stdout.write(JSON.stringify(value) + '\\n');
        let resumeAttempts = 0, userControl = false;
        createInterface({input: process.stdin}).on('line', line => {
          const c = JSON.parse(line);
          if (c.cmd === 'launch') { send({id:c.id, ok:true, chromePid:process.pid}); return; }
          if (mode === 'wedge') {
            const child = spawn('/bin/sleep', ['60'], {stdio:'ignore'});
            writeFileSync('child.pid', String(child.pid));
            process.on('SIGTERM', () => {});
            while (true) {}
          }
          if (mode === 'notReady' && c.cmd === 'setUserControl' && !c.enabled && resumeAttempts++ === 0) {
            send({id:c.id, ok:false, error:'notReady'}); return;
          }
          if (mode === 'hang') return;
          if (mode === 'crash') { process.exit(1); return; }
          if (mode === 'invalid') { send({id:c.id+1, ok:true}); return; }
          if (c.cmd === 'setUserControl') userControl = c.enabled;
          if (c.cmd === 'navigateForHandover') {
            if (!userControl) { send({id:c.id, ok:false, error:'userControlRequired'}); return; }
            if (new URL(c.url).origin !== 'https://example.com') { send({id:c.id, ok:false, error:'originRefused'}); return; }
            writeFileSync('handover-url.txt', c.url);
            send({id:c.id, ok:true}); return;
          }
          if (c.cmd === 'perform') {
            send({event:'mouseMoved', x:40, y:50});
            send({id:c.id, ok:true, rect:{x:10,y:20,width:60,height:60}, matched:'role', viewport});
          } else if (c.cmd === 'check') send({id:c.id, ok:true, satisfied:true});
          else if (c.cmd === 'viewportMetrics') send({id:c.id, ok:true, ...viewport});
          else send({id:c.id, ok:true});
        }).on('close', () => process.exit(0));
        """
        try source.write(to: script, atomically: true, encoding: .utf8)
        return Fixture(directory: directory, host: PlaywrightBrowserHost(nodeURL: URL(fileURLWithPath: node), scriptURL: script, workingDirectory: directory))
    }

    private func run(_ body: @escaping @Sendable () async throws -> Void) {
        let done = expectation(description: "stdio command completed")
        Task {
            do { try await body() } catch { XCTFail("Unexpected adapter error: \(error)") }
            done.fulfill()
        }
        wait(for: [done], timeout: 25)
    }

    func testCorrelatedResponsesMetricsEventsAndExplicitHandover() throws {
        let f = try fixture()
        defer { try? FileManager.default.removeItem(at: f.directory) }
        run {
            _ = try await f.host.launch(f.configuration)
            let outcome = try await f.host.perform(.click(.init(candidates: [.init(role: "button", name: "Create")])), pacing: .rehearsal)
            XCTAssertEqual(outcome.rect?.x, 10)
            XCTAssertEqual(outcome.viewport.devicePixelRatio, 2)
            var iterator = f.host.events.makeAsyncIterator()
            if case .mouseMoved(let point) = await iterator.next() { XCTAssertEqual(point.x, 40) }
            else { XCTFail("Expected pointer event") }
            let metrics = try await f.host.viewportMetrics()
            XCTAssertEqual(metrics.width, 1280)
            try await f.host.setUserControl(true)
            do { _ = try await f.host.perform(.wait(seconds: 0), pacing: .rehearsal); XCTFail("Automation allowed during handover") }
            catch { XCTAssertEqual(error as? BrowserHostError, .refused("userControl")) }
            let satisfied = try await f.host.check(.init(url: "/dashboard"), timeout: 0)
            XCTAssertTrue(satisfied)
            try await f.host.setUserControl(false)
            do { _ = try await f.host.perform(.handover(reason: .login, doneWhen: nil), pacing: .rehearsal); XCTFail("Implicit handover allowed") }
            catch { XCTAssertEqual(error as? BrowserHostError, .refused("explicitUserControlRequired")) }
            await f.host.close()
        }
    }

    func testHandoverNavigationRequiresUserControlAndDoesNotEnableOtherActions() throws {
        let f = try fixture()
        defer { try? FileManager.default.removeItem(at: f.directory) }
        run {
            _ = try await f.host.launch(f.configuration)
            let destination = URL(string: "https://example.com/sign-in")!
            do { try await f.host.navigateForHandover(to: destination); XCTFail("Navigation outside UserControl") }
            catch { XCTAssertEqual(error as? BrowserHostError, .refused("userControlRequired")) }
            try await f.host.setUserControl(true)
            for raw in ["file:///tmp/fixture", "https://user:credential@example.com"] {
                do { try await f.host.navigateForHandover(to: URL(string: raw)!); XCTFail("Unsafe initial URL accepted") }
                catch { XCTAssertTrue(error is DemoSpecError) }
            }
            do { try await f.host.navigateForHandover(to: URL(string: "https://other.example")!); XCTFail("Disallowed initial origin accepted") }
            catch { XCTAssertEqual(error as? BrowserHostError, .refused("originRefused")) }
            try await f.host.navigateForHandover(to: destination)
            XCTAssertEqual(try String(contentsOf: f.directory.appendingPathComponent("handover-url.txt"), encoding: .utf8), destination.absoluteString)
            do { _ = try await f.host.perform(.goto(destination), pacing: .rehearsal); XCTFail("Other actions allowed during handover") }
            catch { XCTAssertEqual(error as? BrowserHostError, .refused("userControl")) }
            try await f.host.setUserControl(false)
            do { try await f.host.navigateForHandover(to: destination); XCTFail("Navigation after Resume") }
            catch { XCTAssertEqual(error as? BrowserHostError, .refused("userControlRequired")) }
            await f.host.close()
        }
    }

    func testPrematureResumeIsRecoverableAndRetainsUserControl() throws {
        let f = try fixture(mode: "notReady")
        defer { try? FileManager.default.removeItem(at: f.directory) }
        run {
            let session = try await f.host.launch(f.configuration)
            try await f.host.setUserControl(true)
            do { try await f.host.setUserControl(false); XCTFail("Premature Resume succeeded") }
            catch { XCTAssertEqual(error as? BrowserHostError, .refused("notReady")) }
            XCTAssertEqual(kill(session.chromeProcessID, 0), 0)
            do { _ = try await f.host.perform(.wait(seconds: 0), pacing: .rehearsal); XCTFail("Lost user-control state") }
            catch { XCTAssertEqual(error as? BrowserHostError, .refused("userControl")) }
            let satisfied = try await f.host.check(.init(url: "/ready"), timeout: 0)
            XCTAssertTrue(satisfied)
            try await f.host.setUserControl(false)
            let outcome = try await f.host.perform(.wait(seconds: 0), pacing: .rehearsal)
            XCTAssertEqual(outcome.viewport.width, 1280)
            await f.host.close()
        }
    }

    func testCancellationClosesStalledProcessAndReleasesPendingCommand() throws {
        let f = try fixture(mode: "hang")
        defer { try? FileManager.default.removeItem(at: f.directory) }
        run {
            let session = try await f.host.launch(f.configuration)
            let command = Task { try await f.host.perform(.wait(seconds: 120), pacing: .rehearsal) }
            try await Task.sleep(for: .milliseconds(100))
            command.cancel()
            do { _ = try await command.value; XCTFail("Cancelled command succeeded") }
            catch { XCTAssertTrue(error is CancellationError) }
            await f.host.close()
            try await Task.sleep(for: .seconds(1))
            XCTAssertEqual(kill(session.chromeProcessID, 0), -1)
            do { _ = try await f.host.viewportMetrics(); XCTFail("Host remained live") }
            catch { XCTAssertEqual(error as? BrowserHostError, .notRunning) }
        }
    }

    func testCloseKillsWedgedHostAndItsDescendants() throws {
        let f = try fixture(mode: "wedge")
        defer { try? FileManager.default.removeItem(at: f.directory) }
        run {
            let session = try await f.host.launch(f.configuration)
            let command = Task { try await f.host.perform(.wait(seconds: 120), pacing: .rehearsal) }
            let pidFile = f.directory.appendingPathComponent("child.pid")
            for _ in 0..<100 {
                if FileManager.default.fileExists(atPath: pidFile.path) { break }
                try await Task.sleep(for: .milliseconds(20))
            }
            let childPID = try XCTUnwrap(Int32(String(contentsOf: pidFile, encoding: .utf8)))
            defer { kill(childPID, SIGKILL) }
            await f.host.close()
            do { _ = try await command.value; XCTFail("Closed command succeeded") }
            catch { XCTAssertEqual(error as? BrowserHostError, .terminated) }
            try await Task.sleep(for: .seconds(4))
            XCTAssertEqual(kill(session.chromeProcessID, 0), -1)
            XCTAssertEqual(kill(childPID, 0), -1)
        }
    }

    func testTransportTimeoutClosesStalledProcess() throws {
        let f = try fixture(mode: "hang")
        defer { try? FileManager.default.removeItem(at: f.directory) }
        run {
            let session = try await f.host.launch(f.configuration)
            do { _ = try await f.host.check(.init(url: "/ready"), timeout: 0); XCTFail("Stalled check succeeded") }
            catch { XCTAssertEqual(error as? BrowserHostError, .timedOut) }
            await f.host.close()
            try await Task.sleep(for: .seconds(1))
            XCTAssertEqual(kill(session.chromeProcessID, 0), -1)
        }
    }

    func testMalformedResponseAndProcessExitFailPendingRequest() throws {
        for mode in ["invalid", "crash"] {
            let f = try fixture(mode: mode)
            defer { try? FileManager.default.removeItem(at: f.directory) }
            run {
                _ = try await f.host.launch(f.configuration)
                do { _ = try await f.host.viewportMetrics(); XCTFail("Broken transport succeeded") }
                catch { XCTAssertEqual(error as? BrowserHostError, mode == "invalid" ? .invalidResponse : .terminated) }
                await f.host.close()
            }
        }
    }
}
