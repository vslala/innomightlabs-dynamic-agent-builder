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

    static var isConfigured: Bool {
        guard
            let agentID, !agentID.isEmpty,
            let apiKey, !apiKey.isEmpty,
            URL(string: baseURL) != nil
        else { return false }
        return true
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
