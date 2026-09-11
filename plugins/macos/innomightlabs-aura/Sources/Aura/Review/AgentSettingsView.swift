import SwiftUI

/// Connection details for the InnomightLabs agent. The API key is stored in the Keychain.
struct AgentSettingsView: View {
    @Environment(\.dismiss) private var dismiss

    @State private var baseURL = AgentSettings.baseURL
    @State private var agentID = AgentSettings.agentID ?? ""
    @State private var apiKey = AgentSettings.apiKey ?? ""
    @State private var isTesting = false
    @State private var outcome: AgentConnectionCheck.Outcome?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Agent Settings")
                .font(.headline)

            Form {
                TextField("API base URL", text: $baseURL)
                SecureField("Agent API key (pk_live_…)", text: $apiKey)
                TextField("Agent ID (discovered from the key)", text: $agentID)
            }
            .textFieldStyle(.roundedBorder)

            HStack(spacing: 8) {
                Button("Test Connection") { test() }
                    .disabled(isTesting || apiKey.trimmingCharacters(in: .whitespaces).isEmpty)

                if isTesting {
                    ProgressView().controlSize(.small)
                } else if let outcome {
                    Label(
                        outcome.message,
                        systemImage: outcome.isUsable ? "checkmark.circle.fill" : "exclamationmark.triangle.fill"
                    )
                    .font(.caption)
                    .foregroundStyle(outcome.isUsable ? .green : .orange)
                    .fixedSize(horizontal: false, vertical: true)
                }
            }

            Text("""
            Create an API key for your agent in the InnomightLabs dashboard and enable \
            Agent2Agent sharing on it. Testing the connection fills in the agent ID for you \
            and confirms sharing is on. The key is stored in your Keychain, never in a file.
            """)
            .font(.caption2)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)

            HStack {
                Spacer()
                Button("Cancel") { dismiss() }
                Button("Save") { save() }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(16)
        .frame(width: 440)
    }

    private func test() {
        isTesting = true
        outcome = nil
        let base = baseURL.trimmingCharacters(in: .whitespaces)
        let key = apiKey.trimmingCharacters(in: .whitespaces)
        let id = agentID.trimmingCharacters(in: .whitespaces)

        Task {
            let result = await AgentConnectionCheck.run(baseURL: base, agentID: id, apiKey: key)
            isTesting = false
            outcome = result
            if let discovered = result.agentID, agentID.isEmpty {
                agentID = discovered
            }
        }
    }

    private func save() {
        AgentSettings.baseURL = baseURL.trimmingCharacters(in: .whitespaces)
        AgentSettings.agentID = agentID.trimmingCharacters(in: .whitespaces)
        AgentSettings.apiKey = apiKey.trimmingCharacters(in: .whitespaces)
        dismiss()
    }
}
