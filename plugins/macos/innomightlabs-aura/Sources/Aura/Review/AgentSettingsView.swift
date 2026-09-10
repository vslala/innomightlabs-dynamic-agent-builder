import SwiftUI

/// Connection details for the InnomightLabs agent. The API key is stored in the Keychain.
struct AgentSettingsView: View {
    @Environment(\.dismiss) private var dismiss

    @State private var baseURL = AgentSettings.baseURL
    @State private var agentID = AgentSettings.agentID ?? ""
    @State private var apiKey = AgentSettings.apiKey ?? ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Agent Settings")
                .font(.headline)

            Form {
                TextField("API base URL", text: $baseURL)
                TextField("Agent ID", text: $agentID)
                SecureField("Agent API key (pk_live_…)", text: $apiKey)
            }
            .textFieldStyle(.roundedBorder)

            Text("""
            Create an API key for your agent in the InnomightLabs dashboard and enable \
            Agent2Agent sharing on it. Leave the key's allowed origins empty — a desktop app \
            sends no Origin header. The key is stored in your Keychain.
            """)
            .font(.caption2)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)

            HStack {
                Spacer()
                Button("Cancel") { dismiss() }
                Button("Save") {
                    AgentSettings.baseURL = baseURL.trimmingCharacters(in: .whitespaces)
                    AgentSettings.agentID = agentID.trimmingCharacters(in: .whitespaces)
                    AgentSettings.apiKey = apiKey.trimmingCharacters(in: .whitespaces)
                    dismiss()
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(16)
        .frame(width: 420)
    }
}
