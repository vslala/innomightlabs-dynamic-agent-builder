import Foundation

/// The root is injected so UI, agent and tests share the same persistence rules.
struct DemoSpecStore: Sendable {
    let rootDirectory: URL

    func directory(for id: UUID) -> URL { rootDirectory.appendingPathComponent(id.uuidString, isDirectory: true) }
    func profileDirectory(for id: UUID) -> URL { directory(for: id).appendingPathComponent("profile", isDirectory: true) }

    /// Every saved demo, by title. One that cannot be read is left out rather than failing the list.
    func list() -> [DemoSpec] {
        let folders = (try? FileManager.default.contentsOfDirectory(at: rootDirectory, includingPropertiesForKeys: nil)) ?? []
        return folders
            .compactMap { UUID(uuidString: $0.lastPathComponent) }
            .compactMap { try? load(id: $0) }
            .sorted { $0.title.localizedStandardCompare($1.title) == .orderedAscending }
    }

    /// Removes the spec and, with it, the dedicated Chrome profile: its cookies are the user's
    /// sign-in to the demo site, and nothing else should keep them.
    func delete(id: UUID) throws {
        try FileManager.default.removeItem(at: directory(for: id))
    }

    func load(id: UUID) throws -> DemoSpec {
        let spec = try load(from: directory(for: id).appendingPathComponent("spec.json"))
        guard spec.id == id else { throw DemoSpecError.invalid("Demo identity does not match its folder") }
        return spec
    }

    func load(from url: URL) throws -> DemoSpec {
        // Bound the read itself, not just decoding, including files that grow during the read.
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let data = try handle.read(upToCount: DemoSpec.maximumBytes + 1) ?? Data()
        guard data.count <= DemoSpec.maximumBytes else { throw DemoSpecError.invalid("Demo file exceeds size limit") }
        return try JSONDecoder().decode(DemoSpec.self, from: data)
    }

    @discardableResult
    func save(_ spec: DemoSpec) throws -> DemoSpec {
        try spec.validate()
        var saved = spec
        let destination = directory(for: spec.id).appendingPathComponent("spec.json")
        if FileManager.default.fileExists(atPath: destination.path) {
            let previous = try load(id: spec.id)
            guard previous.revision == spec.revision else { throw DemoSpecError.invalid("Demo revision changed; reload before saving") }
        }
        saved.revision += 1
        let data = try encoded(saved)
        try FileManager.default.createDirectory(at: directory(for: spec.id), withIntermediateDirectories: true)
        try data.write(to: destination, options: .atomic)
        return saved
    }

    /// Copies the exact replayed revision; never bumps it or copies cookies/profile data.
    func copy(_ spec: DemoSpec, into sessionDirectory: URL) throws {
        try encoded(spec).write(to: sessionDirectory.appendingPathComponent("demo-spec.json"), options: .atomic)
    }

    private func encoded(_ spec: DemoSpec) throws -> Data {
        try spec.validate()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        let data = try encoder.encode(spec)
        guard data.count <= DemoSpec.maximumBytes else { throw DemoSpecError.invalid("Demo file exceeds size limit") }
        return data
    }
}
