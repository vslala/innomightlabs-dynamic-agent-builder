import XCTest
@testable import Aura

/// Answers requests from a per-test table of path -> (status, JSON), and records what was sent.
private final class StubURLProtocol: URLProtocol {
    nonisolated(unsafe) static var responses: [String: (Int, String)] = [:]
    nonisolated(unsafe) static var requests: [URLRequest] = []

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.requests.append(request)
        let (status, body) = Self.responses[request.url?.path ?? ""] ?? (404, #"{"detail":"Not Found"}"#)
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

final class AgentConnectionCheckTests: XCTestCase {
    private var session: URLSession!

    override func setUp() {
        super.setUp()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubURLProtocol.self]
        session = URLSession(configuration: configuration)
        StubURLProtocol.requests = []
        StubURLProtocol.responses = [
            "/widget/config": (200, #"{"agent_id":"agent-1","agent_name":"Key"}"#),
            "/a2a/agents/agent-1/card": (200, #"{"name":"Editor"}"#),
            "/a2a/agents/agent-1": (200, #"{"jsonrpc":"2.0","id":"1","result":{"tasks":[]}}"#)
        ]
    }

    private func run(secret: String = "a2a_live_abc") async -> AgentConnectionCheck.Outcome {
        await AgentConnectionCheck.run(
            baseURL: "https://api.example.com",
            agentID: nil,
            apiKey: "pk_live_abc",
            a2aSecret: secret,
            session: session
        )
    }

    func testConnectsWhenKeyCardAndSecretAllCheckOut() async {
        let outcome = await run()

        XCTAssertTrue(outcome.isUsable)
        XCTAssertEqual(outcome.agentID, "agent-1")
        XCTAssertEqual(outcome.agentName, "Editor")
    }

    func testEachCredentialGoesWhereTheServerExpectsIt() async {
        _ = await run()

        let discovery = StubURLProtocol.requests.first { $0.url?.path == "/widget/config" }
        XCTAssertEqual(discovery?.value(forHTTPHeaderField: "X-API-Key"), "pk_live_abc")

        let a2a = StubURLProtocol.requests.first { $0.url?.path == "/a2a/agents/agent-1" }
        XCTAssertEqual(a2a?.value(forHTTPHeaderField: "Authorization"), "Bearer a2a_live_abc")
    }

    func testRejectedSecretIsNotReportedAsConnected() async {
        // The regression this guards: discovery and the card pass without the secret, so a
        // check that stopped there said "Connected" and every edit then failed with a 401.
        StubURLProtocol.responses["/a2a/agents/agent-1"] = (401, #"{"detail":"Invalid A2A credential"}"#)

        let outcome = await run()

        XCTAssertFalse(outcome.isUsable)
        XCTAssertTrue(outcome.isA2AEnabled)
        XCTAssertEqual(outcome.agentID, "agent-1")
    }

    func testMissingSecretStopsBeforeAnyRequest() async {
        let outcome = await run(secret: "")

        XCTAssertFalse(outcome.isUsable)
        XCTAssertTrue(StubURLProtocol.requests.isEmpty)
    }

    func testPublicAPISecretKeyIsNamedRatherThanSentToA2A() async {
        let outcome = await run(secret: "sk_live_abc")

        XCTAssertFalse(outcome.isUsable)
        XCTAssertTrue(outcome.message.contains("a2a_live_"))
        XCTAssertTrue(StubURLProtocol.requests.isEmpty)
    }

    func testSharingOffIsReportedBeforeTheSecretIsTried() async {
        StubURLProtocol.responses["/a2a/agents/agent-1/card"] = (404, #"{"detail":"Agent not found"}"#)

        let outcome = await run()

        XCTAssertFalse(outcome.isUsable)
        XCTAssertFalse(outcome.isA2AEnabled)
        XCTAssertFalse(StubURLProtocol.requests.contains { $0.url?.path == "/a2a/agents/agent-1" })
    }
}
