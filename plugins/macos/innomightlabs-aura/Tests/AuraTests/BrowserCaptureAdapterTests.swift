import XCTest
@testable import Aura

/// The Swift end of the demonstration protocol, against a stand-in for the Node host that sends the
/// exact messages the real one does (`BrowserHostChrome.test.mjs` pins those against real Chrome).
final class BrowserCaptureAdapterTests: XCTestCase {
    private func fixture(extra: String = "") throws -> (host: PlaywrightBrowserHost, directory: URL) {
        guard let node = ["/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node"]
            .first(where: { FileManager.default.isExecutableFile(atPath: $0) }) else { throw XCTSkip("Node is not installed") }
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("capture-adapter-\(UUID())")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let script = directory.appendingPathComponent("fake.mjs")
        try """
        import { createInterface } from 'node:readline';
        import { writeFileSync } from 'node:fs';
        const send = value => process.stdout.write(JSON.stringify(value) + '\\n');
        createInterface({input: process.stdin}).on('line', line => {
          const c = JSON.parse(line);
          if (c.cmd === 'launch') { writeFileSync('launch.json', line); send({id:c.id, ok:true, chromePid:process.pid}); return; }
          if (c.cmd === 'flushCapture') {
            send({event:'captured', interaction:{kind:'scroll', x:0, y:100}});
            send({id:c.id, ok:true, interactions:[{kind:'scroll', x:20, y:300, target:{candidates:[{testId:'panel'}]}}]});
            return;
          }
          if (c.cmd === 'navigateForHandover') {
            send({id:c.id, ok:true});
            send({event:'navigated', url:'https://example.com/dashboard', clean:true});
            send({event:'captured', interaction:{kind:'click', target:{candidates:[{testId:'create-agent'},{role:'button',name:'Create agent'}], hintRect:{x:1,y:2,width:30,height:10}}, rect:{x:1,y:2,width:30,height:10}}});
            send({event:'captured', interaction:{kind:'input', target:{candidates:[{role:'textbox',name:'Website'}]}, value:'https://example.com'}});
            send({event:'captured', interaction:{kind:'press', key:'Enter'}});
            send({event:'captured', interaction:{kind:'scroll', x:0, y:480}});
            send({event:'captured', interaction:{kind:'sensitiveInput'}});
            send({event:'navigated', url:'https://example.com/agents/new', clean:false});
            \(extra)
            return;
          }
          send({id:c.id, ok:true});
        }).on('close', () => process.exit(0));
        """.write(to: script, atomically: true, encoding: .utf8)
        return (PlaywrightBrowserHost(nodeURL: URL(fileURLWithPath: node), scriptURL: script, workingDirectory: directory), directory)
    }

    private func configuration(_ directory: URL, capture: Bool) -> BrowserLaunch {
        BrowserLaunch(profileDirectory: directory.appendingPathComponent("profile"), startURL: URL(string: "https://example.com/start")!,
                      window: .init(width: 1440, height: 900), allowedOrigins: ["https://example.com"], capture: capture)
    }

    private func collect(_ host: PlaywrightBrowserHost, count: Int) async -> [BrowserEvent] {
        var events: [BrowserEvent] = []
        for await event in host.events {
            events.append(event)
            if events.count == count { break }
        }
        return events
    }

    func testFlushReturnsPendingTargetedScrollWithoutDuplicatingItOnTheStream() async throws {
        let (host, directory) = try fixture()
        defer { try? FileManager.default.removeItem(at: directory) }
        _ = try await host.launch(configuration(directory, capture: true))
        let pending = try await host.flushCapture()
        XCTAssertEqual(pending, [.scroll(.init(x: 20, y: 300, target: .init(candidates: [.init(testId: "panel")])) )])
        let events = await collect(host, count: 2)
        XCTAssertEqual(events, [.interaction(.scroll(.init(x: 0, y: 100))), .captureFlushed])
        await host.close()
        let closedPending = try await host.flushCapture()
        XCTAssertEqual(closedPending, [])
    }

    func testTheLaunchRequestAsksForCaptureAndTheEventsDecodeIntoTypedInteractions() async throws {
        let (host, directory) = try fixture()
        defer { try? FileManager.default.removeItem(at: directory) }
        _ = try await host.launch(configuration(directory, capture: true))
        let launch = try JSONSerialization.jsonObject(with: Data(contentsOf: directory.appendingPathComponent("launch.json"))) as? [String: Any]
        XCTAssertEqual(launch?["capture"] as? Bool, true)

        try await host.navigateForHandover(to: URL(string: "https://example.com/start")!)
        let events = await collect(host, count: 7)
        XCTAssertEqual(events, [
            .navigated(URL(string: "https://example.com/dashboard")!, clean: true),
            .interaction(.click(
                ElementTarget(candidates: [LocatorCandidate(testId: "create-agent"), LocatorCandidate(role: "button", name: "Create agent")],
                              hintRect: BrowserRect(x: 1, y: 2, width: 30, height: 10)),
                rect: BrowserRect(x: 1, y: 2, width: 30, height: 10))),
            .interaction(.input(ElementTarget(candidates: [LocatorCandidate(role: "textbox", name: "Website")]), value: "https://example.com")),
            .interaction(.press(key: "Enter")),
            .interaction(.scroll(ScrollPosition(x: 0, y: 480))),
            .interaction(.sensitiveInput),
            .navigated(URL(string: "https://example.com/agents/new")!, clean: false)
        ])
        await host.close()
    }

    func testEventsAreNotMutedDuringADemonstrationButAreDuringAHandover() async throws {
        let (host, directory) = try fixture()
        defer { try? FileManager.default.removeItem(at: directory) }
        _ = try await host.launch(configuration(directory, capture: true))
        try await host.navigateForHandover(to: URL(string: "https://example.com/start")!)
        let events = await collect(host, count: 1)
        XCTAssertEqual(events.count, 1, "the user's own actions are the point, so nothing is held back")
        await host.close()
    }

    func testAnAutomatedActionIsRefusedWhileADemonstrationIsRecorded() async throws {
        let (host, directory) = try fixture()
        defer { try? FileManager.default.removeItem(at: directory) }
        _ = try await host.launch(configuration(directory, capture: true))
        do {
            _ = try await host.perform(.wait(seconds: 0), pacing: .rehearsal)
            XCTFail("Aura must not drive the browser while the user does")
        } catch { XCTAssertEqual(error as? BrowserHostError, .refused("userControl")) }
        do { _ = try await host.snapshot(); XCTFail() }
        catch { XCTAssertEqual(error as? BrowserHostError, .refused("userControl")) }
        await host.close()
    }

    func testOrdinaryLaunchesStillSayTheyAreNotCapturing() async throws {
        let (host, directory) = try fixture()
        defer { try? FileManager.default.removeItem(at: directory) }
        _ = try await host.launch(configuration(directory, capture: false))
        let launch = try JSONSerialization.jsonObject(with: Data(contentsOf: directory.appendingPathComponent("launch.json"))) as? [String: Any]
        XCTAssertEqual(launch?["capture"] as? Bool, false)
        await host.close()
    }

    func testAnInteractionTheAppDoesNotUnderstandStopsTheHostInsteadOfBeingGuessedAt() async throws {
        let (host, directory) = try fixture(extra: "send({event:'captured', interaction:{kind:'teleport'}});")
        defer { try? FileManager.default.removeItem(at: directory) }
        _ = try await host.launch(configuration(directory, capture: true))
        try await host.navigateForHandover(to: URL(string: "https://example.com/start")!)
        var sawClose = false
        for await event in host.events {
            if case .closed = event { sawClose = true; break }
        }
        XCTAssertTrue(sawClose, "a protocol error ends the session rather than recording something invented")
    }
}
