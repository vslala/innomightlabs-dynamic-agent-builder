import Foundation
import Security

/// Where the InnomightLabs agent lives and how to authenticate to it.
///
/// The API key goes in the Keychain, everything else in `UserDefaults` under the `Aura.`
/// prefix this app already uses for preferences.
enum AgentSettings {
    private static let baseURLKey = "Aura.agentBaseURL"
    private static let agentIDKey = "Aura.agentID"
    private static let keychainAccount = "innomightlabs-agent-api-key"

    static let defaultBaseURL = "https://api.innomightlabs.com"

    static var baseURL: String {
        get { UserDefaults.standard.string(forKey: baseURLKey) ?? defaultBaseURL }
        set { UserDefaults.standard.set(newValue, forKey: baseURLKey) }
    }

    static var agentID: String? {
        get { UserDefaults.standard.string(forKey: agentIDKey) }
        set { UserDefaults.standard.set(newValue, forKey: agentIDKey) }
    }

    static var apiKey: String? {
        get { Keychain.read(account: keychainAccount) }
        set {
            if let newValue, !newValue.isEmpty {
                Keychain.write(newValue, account: keychainAccount)
            } else {
                Keychain.delete(account: keychainAccount)
            }
        }
    }

    /// Environment overrides, for scripts and tests. The app itself relies on the Keychain,
    /// because a GUI app launched from Finder or via `open` inherits no shell environment.
    private static func environment(_ name: String) -> String? {
        guard let value = ProcessInfo.processInfo.environment[name], !value.isEmpty else { return nil }
        return value
    }

    static var resolvedBaseURL: String { environment("AURA_AGENT_BASE_URL") ?? baseURL }
    static var resolvedAgentID: String? { environment("AURA_AGENT_ID") ?? agentID }
    static var resolvedAPIKey: String? { environment("AURA_AGENT_API_KEY") ?? apiKey }

    static var isConfigured: Bool { (try? resolved()) != nil }

    /// Everything a request needs, validated once so callers don't each re-check.
    struct Resolved {
        let baseURL: URL
        let agentID: String
        let apiKey: String

        /// A2A JSON-RPC endpoint for this agent.
        var messageEndpoint: URL { baseURL.appendingPathComponent("a2a/agents/\(agentID)") }
        var cardEndpoint: URL { baseURL.appendingPathComponent("a2a/agents/\(agentID)/card") }
        var widgetConfigEndpoint: URL { baseURL.appendingPathComponent("widget/config") }
    }

    static func resolved() throws -> Resolved {
        guard
            let baseURL = URL(string: resolvedBaseURL), baseURL.scheme != nil,
            let agentID = resolvedAgentID, !agentID.isEmpty,
            let apiKey = resolvedAPIKey, !apiKey.isEmpty
        else { throw EditSuggestionError.notConfigured }

        return Resolved(baseURL: baseURL, agentID: agentID, apiKey: apiKey)
    }
}

/// Minimal generic-password wrapper. A credential does not belong in `UserDefaults`.
enum Keychain {
    private static let service = "com.innomightlabs.aura"

    static func read(account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var item: CFTypeRef?
        guard
            SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
            let data = item as? Data
        else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func write(_ value: String, account: String) {
        delete(account: account)
        let attributes: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecValueData as String: Data(value.utf8)
        ]
        SecItemAdd(attributes as CFDictionary, nil)
    }

    static func delete(account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }
}
