import Foundation
import Darwin

/// One in-flight command. Cancellation or transport timeout tears down the whole session: a
/// partially executed click/type must never continue invisibly after ReplayEngine has stopped.
actor PlaywrightBrowserHost: BrowserDriving {
    nonisolated let events: AsyncStream<BrowserEvent>
    private let eventContinuation: AsyncStream<BrowserEvent>.Continuation
    private let nodeURL: URL
    private let scriptURL: URL
    private let workingDirectory: URL
    private var process: Process?
    private var input: FileHandle?
    private var output: FileHandle?
    private var reader: Task<Void, Never>?
    private var timeoutTask: Task<Void, Never>?
    private var buffer = Data()
    private var nextID = 0
    private var pending: (id: Int, continuation: CheckedContinuation<Data, Error>)?
    private var userControl = false
    private var capturing = false
    private var generation = UUID()

    init(nodeURL: URL, scriptURL: URL, workingDirectory: URL) {
        self.nodeURL = nodeURL; self.scriptURL = scriptURL; self.workingDirectory = workingDirectory
        let stream = AsyncStream<BrowserEvent>.makeStream(bufferingPolicy: .bufferingNewest(16384))
        events = stream.stream; eventContinuation = stream.continuation
    }

    deinit {
        reader?.cancel(); timeoutTask?.cancel()
        output?.readabilityHandler = nil
        try? input?.close(); try? output?.close()
        if let process, process.isRunning { Self.terminate(process) }
        eventContinuation.finish()
    }

    func launch(_ configuration: BrowserLaunch) async throws -> BrowserSession {
        guard process == nil else { throw BrowserHostError.busy }
        guard configuration.profileDirectory.isFileURL else { throw DemoSpecError.invalid("Profile must be a local directory") }
        // Reuse spec validation at the transport boundary, including callers that do not load a file.
        try DemoSpec(title: "Browser", startURL: configuration.startURL, allowedOrigins: configuration.allowedOrigins,
                     window: configuration.window, steps: [.init(id: "launch", action: .wait(seconds: 0), intent: "Launch")]).validate()
        try start()
        var request = Request(cmd: "launch")
        request.profileDir = configuration.profileDirectory.path
        request.startURL = configuration.startURL; request.window = configuration.window
        request.allowedOrigins = configuration.allowedOrigins; request.capture = configuration.capture
        do {
            let response: LaunchResponse = try await send(request, timeout: 40)
            guard response.chromePid > 0 else { throw BrowserHostError.invalidResponse }
            capturing = configuration.capture
            return BrowserSession(chromeProcessID: response.chromePid)
        } catch { stop(error: error); throw error }
    }

    func perform(_ action: DemoAction, pacing: ActionPacing) async throws -> ActionOutcome {
        guard !userControl, !capturing else { throw BrowserHostError.refused("userControl") }
        if case .handover = action { throw BrowserHostError.refused("explicitUserControlRequired") }
        var request = Request(cmd: "perform"); request.action = action; request.pacing = pacing
        return try await send(request, timeout: 140)
    }

    func check(_ expectation: Expectation, timeout: TimeInterval) async throws -> Bool {
        guard timeout.isFinite && (0...120).contains(timeout) else { throw DemoSpecError.invalid("Invalid expectation timeout") }
        var request = Request(cmd: "check"); request.expectation = expectation; request.timeout = timeout
        let response: CheckResponse = try await send(request, timeout: timeout + 10)
        return response.satisfied
    }

    func setUserControl(_ enabled: Bool) async throws {
        // Suppress late queued content events immediately on entry, not only after the response.
        if enabled { userControl = true }
        var request = Request(cmd: "setUserControl"); request.enabled = enabled
        do {
            let _: EmptyResponse = try await send(request, timeout: 15)
            userControl = enabled
        } catch {
            // ReplayEngine stays in UserControl and offers Resume again after login completes.
            if !enabled, error as? BrowserHostError == .refused("notReady") { throw error }
            stop(error: error)
            throw error
        }
    }

    func navigateForHandover(to url: URL) async throws {
        // A demonstration holds the browser with the user throughout; the host enforces it too.
        guard userControl || capturing else { throw BrowserHostError.refused("userControlRequired") }
        _ = try DemoSpec.origin(of: url)
        var request = Request(cmd: "navigateForHandover"); request.url = url
        let _: EmptyResponse = try await send(request, timeout: 30)
    }

    func viewportMetrics() async throws -> BrowserViewportMetrics {
        try await send(Request(cmd: "viewportMetrics"), timeout: 15)
    }

    func showCalibrationPage() async throws -> BrowserCalibration {
        try await send(Request(cmd: "showCalibrationPage"), timeout: 30)
    }

    func snapshot() async throws -> String {
        guard !userControl, !capturing else { throw BrowserHostError.refused("userControl") }
        let response: SnapshotResponse = try await send(Request(cmd: "snapshot"), timeout: 15)
        return response.snapshot
    }

    func flushCapture() async throws -> [CapturedInteraction] {
        guard process?.isRunning == true, capturing else {
            eventContinuation.yield(.captureFlushed)
            return []
        }
        do {
            let response: FlushResponse = try await send(Request(cmd: "flushCapture"), timeout: 15)
            let interactions = try response.interactions.map { raw in
                guard let interaction = raw.parsed else { throw BrowserHostError.invalidResponse }
                return interaction
            }
            eventContinuation.yield(.captureFlushed)
            return interactions
        } catch {
            eventContinuation.yield(.captureFlushed)
            // Closing Chrome is a valid way to finish a demonstration.
            if let error = error as? BrowserHostError,
               [.notRunning, .terminated, .refused("notRunning")].contains(error) { return [] }
            throw error
        }
    }

    func close() async { stop(error: BrowserHostError.terminated) }

    private func start() throws {
        let child = Process(), stdinPipe = Pipe(), stdoutPipe = Pipe()
        child.executableURL = nodeURL; child.arguments = [scriptURL.path]
        child.currentDirectoryURL = workingDirectory
        child.standardInput = stdinPipe; child.standardOutput = stdoutPipe
        // Browser stderr can contain URLs or page values. It is intentionally never retained/logged.
        child.standardError = FileHandle.nullDevice
        let chunks = AsyncStream<Data>.makeStream(bufferingPolicy: .bufferingOldest(64))
        let token = UUID(); generation = token
        stdoutPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty { chunks.continuation.finish() }
            else if case .dropped = chunks.continuation.yield(data) { chunks.continuation.finish() }
        }
        child.terminationHandler = { _ in chunks.continuation.finish() }
        do { try child.run() }
        catch {
            stdoutPipe.fileHandleForReading.readabilityHandler = nil
            chunks.continuation.finish()
            throw BrowserHostError.unavailable
        }
        process = child; input = stdinPipe.fileHandleForWriting; output = stdoutPipe.fileHandleForReading
        reader = Task { [weak self] in
            for await data in chunks.stream {
                guard !Task.isCancelled else { break }
                await self?.receive(data, generation: token)
            }
            await self?.transportEnded(generation: token)
        }
    }

    private func send<T: Decodable>(_ request: Request, timeout: TimeInterval) async throws -> T {
        try Task.checkCancellation()
        guard process?.isRunning == true, let input else { throw BrowserHostError.notRunning }
        guard pending == nil else { throw BrowserHostError.busy }
        nextID += 1
        var request = request; request.id = nextID
        var bytes = try JSONEncoder().encode(request)
        guard bytes.count <= DemoSpec.maximumBytes else { throw DemoSpecError.invalid("Browser request exceeds size limit") }
        bytes.append(10)
        let id = nextID
        let data: Data = try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                pending = (id, continuation)
                timeoutTask = Task { [weak self] in
                    do { try await Task.sleep(for: .seconds(timeout)) } catch { return }
                    await self?.expire(id: id)
                }
                let payload = bytes
                DispatchQueue.global().async { [weak self] in
                    do { try input.write(contentsOf: payload) }
                    catch { Task { await self?.writeFailed(id: id) } }
                }
            }
        } onCancel: {
            Task { await self.cancel(id: id) }
        }
        try Task.checkCancellation()
        do { return try JSONDecoder().decode(T.self, from: data) }
        catch { stop(error: BrowserHostError.invalidResponse); throw BrowserHostError.invalidResponse }
    }

    private func writeFailed(id: Int) {
        if pending?.id == id { stop(error: BrowserHostError.terminated) }
    }

    private func expire(id: Int) {
        if pending?.id == id { stop(error: BrowserHostError.timedOut) }
    }
    private func cancel(id: Int) {
        if pending?.id == id { stop(error: CancellationError()) }
    }
    private func transportEnded(generation token: UUID) {
        if token == generation { stop(error: BrowserHostError.terminated) }
    }

    private func receive(_ data: Data, generation token: UUID) {
        guard token == generation, process != nil else { return }
        buffer.append(data)
        while let newline = buffer.firstIndex(of: 10) {
            let line = Data(buffer[..<newline]); buffer.removeSubrange(...newline)
            guard line.count <= DemoSpec.maximumBytes else { stop(error: BrowserHostError.invalidResponse); return }
            do {
                let message = try JSONDecoder().decode(Message.self, from: line)
                if let event = message.event {
                    if !userControl || event == "closed" { try publish(message) }
                } else {
                    guard let pending, message.id == pending.id, let ok = message.ok else { throw BrowserHostError.invalidResponse }
                    self.pending = nil; timeoutTask?.cancel(); timeoutTask = nil
                    if ok { pending.continuation.resume(returning: line) }
                    else {
                        // Only accept machine codes, never an arbitrary page/Playwright error message.
                        let code = message.error ?? "browserFailure"
                        let safe = code.count <= 64 && code.allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber) }
                        pending.continuation.resume(throwing: BrowserHostError.refused(safe ? code : "browserFailure"))
                    }
                }
            } catch { stop(error: BrowserHostError.invalidResponse); return }
        }
        if buffer.count > DemoSpec.maximumBytes { stop(error: BrowserHostError.invalidResponse) }
    }

    private func publish(_ message: Message) throws {
        let event: BrowserEvent
        switch message.event {
        case "mouseMoved", "mouseDown", "mouseUp":
            guard let x = message.x, let y = message.y, x.isFinite, y.isFinite else { throw BrowserHostError.invalidResponse }
            let point = CGPoint(x: x, y: y)
            if message.event == "mouseMoved" { event = .mouseMoved(to: point) }
            else if message.event == "mouseDown" { event = .mouseDown(at: point) }
            else { event = .mouseUp(at: point) }
        case "navigated", "navigationRefused":
            guard let raw = message.url, let url = URL(string: raw) else { throw BrowserHostError.invalidResponse }
            event = message.event == "navigated" ? .navigated(url, clean: message.clean ?? false) : .navigationRefused(url)
        case "viewportResized":
            guard let width = message.width, let height = message.height, width > 0, height > 0 else { throw BrowserHostError.invalidResponse }
            event = .viewportResized(CGSize(width: width, height: height))
        case "captured":
            guard let interaction = message.interaction?.parsed else { throw BrowserHostError.invalidResponse }
            event = .interaction(interaction)
        case "closed": event = .closed(reason: "Browser closed")
        default: throw BrowserHostError.invalidResponse
        }
        if case .dropped = eventContinuation.yield(event) { stop(error: BrowserHostError.invalidResponse) }
    }

    private func stop(error: Error) {
        let child = process; process = nil; generation = UUID()
        if child != nil { eventContinuation.yield(.closed(reason: "Browser host stopped")) }
        timeoutTask?.cancel(); timeoutTask = nil
        reader?.cancel(); reader = nil
        output?.readabilityHandler = nil
        try? input?.close(); input = nil
        try? output?.close(); output = nil
        buffer.removeAll(); userControl = false; capturing = false
        let waiting = pending; pending = nil
        waiting?.continuation.resume(throwing: error)
        if let child, child.isRunning { Self.terminate(child) }
    }

    private nonisolated static func terminate(_ child: Process) {
        child.terminate()
        // Node normally closes Chrome within 1s. A blocked Node event loop cannot handle SIGTERM,
        // so the fallback must reap its descendants too, before killing their parent.
        DispatchQueue.global().asyncAfter(deadline: .now() + 3) {
            guard child.isRunning else { return }
            let listing = Process(), pipe = Pipe()
            listing.executableURL = URL(fileURLWithPath: "/bin/ps")
            listing.arguments = ["-axo", "pid=,ppid="]
            listing.standardOutput = pipe; listing.standardError = FileHandle.nullDevice
            var descendants: Set<Int32> = [child.processIdentifier]
            if (try? listing.run()) != nil {
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                listing.waitUntilExit()
                let tree = String(decoding: data, as: UTF8.self).split(separator: "\n").compactMap { line -> (Int32, Int32)? in
                    let fields = line.split(whereSeparator: \.isWhitespace)
                    guard fields.count == 2, let pid = Int32(fields[0]), let parent = Int32(fields[1]) else { return nil }
                    return (pid, parent)
                }
                for _ in tree { for (pid, parent) in tree where descendants.contains(parent) { descendants.insert(pid) } }
            }
            guard child.isRunning else { return }
            for pid in descendants where pid != child.processIdentifier { kill(pid, SIGKILL) }
            kill(child.processIdentifier, SIGKILL)
        }
    }

    private struct Request: Encodable {
        var id: Int? = nil
        var cmd: String
        var profileDir: String? = nil
        var startURL: URL? = nil
        var url: URL? = nil
        var window: WindowSize? = nil
        var allowedOrigins: [String]? = nil
        var capture: Bool? = nil
        var action: DemoAction? = nil
        var pacing: ActionPacing? = nil
        var expectation: Expectation? = nil
        var timeout: Double? = nil
        var enabled: Bool? = nil
    }
    private struct Message: Decodable {
        var id: Int?; var ok: Bool?; var error: String?; var event: String?
        var x: Double?; var y: Double?; var url: String?; var width: Double?; var height: Double?
        var clean: Bool?; var interaction: RawInteraction?
    }
    /// The host's description of one thing the user did. Decoded strictly: an unknown kind or a
    /// missing field is a protocol error, not something to guess around.
    private struct RawInteraction: Decodable {
        var kind: String; var target: ElementTarget?; var rect: BrowserRect?
        var value: String?; var key: String?; var x: Double?; var y: Double?

        var parsed: CapturedInteraction? {
            switch kind {
            case "click": if let target, let rect { return .click(target, rect: rect) }
            case "input": if let target, let value { return .input(target, value: value) }
            case "press": if let key { return .press(key: key) }
            case "scroll": if let x, let y, x.isFinite, y.isFinite { return .scroll(ScrollPosition(x: x, y: y, target: target)) }
            case "sensitiveInput": return .sensitiveInput
            default: break
            }
            return nil
        }
    }
    private struct FlushResponse: Decodable { var interactions: [RawInteraction] }
    private struct LaunchResponse: Decodable { var chromePid: Int32 }
    private struct CheckResponse: Decodable { var satisfied: Bool }
    private struct SnapshotResponse: Decodable { var snapshot: String }
    private struct EmptyResponse: Decodable {}
}
