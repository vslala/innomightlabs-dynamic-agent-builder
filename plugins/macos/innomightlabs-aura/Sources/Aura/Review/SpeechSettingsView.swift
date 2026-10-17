import SwiftUI

/// Turning Speech Replacement on and off, and the licence it comes with.
///
/// The model is not part of Aura: this is where it is offered, explained, and — only once the
/// user has agreed — downloaded.
struct SpeechSettingsView: View {
    @ObservedObject var installer: SpeechEngineInstaller

    @State private var cameraWarningSuppressed = SpeechPreferences.suppressesCameraWarning
    @State private var isConfirmingRemoval = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Speech Replacement")
                .font(.headline)

            Text("""
            Type new words for a line of your recording and hear them in your own voice, in \
            place of the original. Everything runs on this Mac; nothing you say or type is sent anywhere.
            """)
            .font(.callout)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)

            switch installer.state {
            case .off: off
            case .awaitingLicence: licence
            case .installing(let fraction): installing(fraction)
            case .ready: ready
            case .failed(let message): failed(message)
            }

            Spacer(minLength: 0)
        }
        .padding(16)
        .frame(width: 440, height: 380, alignment: .topLeading)
        .confirmationDialog("Remove the speech model?", isPresented: $isConfirmingRemoval) {
            Button("Remove", role: .destructive) { installer.uninstall() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This frees about \(megabytes) MB. Sentences already re-spoken keep playing from your recordings' own folders; turning this on again asks for the licence again.")
        }
    }

    private var megabytes: Int { Int(installer.bundle.totalBytes / 1_000_000) }

    // MARK: - States

    private var off: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("It needs a voice model of about \(megabytes) MB, which is downloaded once, from its publisher, after you have read its licence.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Button("Turn On…") { installer.beginEnabling() }
                .keyboardShortcut(.defaultAction)
        }
    }

    private var licence: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Before you download the model")
                .font(.subheadline.weight(.semibold))

            Text("""
            The voice model is published by others under \(installer.bundle.licenceName). \
            In short, it may be used for **non-commercial** purposes only. That includes using it, \
            and sharing what you make with it, without charge; it does not include selling that \
            audio or using it in a commercial product. What you make with it is your \
            responsibility, so read the licence before you publish anything commercially.
            """)
            .font(.callout)
            .fixedSize(horizontal: false, vertical: true)

            Text("Use it only with your own voice, or a voice you have permission to use. Never to pass off words as someone else's.")
                .font(.callout)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 16) {
                Link("Read the full licence", destination: installer.bundle.licenceURL)
                Link("Model page", destination: installer.bundle.modelCardURL)
            }
            .font(.callout)

            Text("Download: \(megabytes) MB")
                .font(.caption)
                .foregroundStyle(.secondary)

            HStack {
                Spacer()
                Button("Not Now") { installer.declineLicence() }
                Button("Agree and Download") { installer.acceptLicence() }
                    .keyboardShortcut(.defaultAction)
            }
        }
    }

    private func installing(_ fraction: Double) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            ProgressView(value: fraction)
            Text(String(format: "Downloading the voice model… %.0f%%", fraction * 100))
                .font(.caption)
                .foregroundStyle(.secondary)
            Button("Cancel") { installer.cancelInstall() }
        }
    }

    private var ready: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Speech Replacement is on", systemImage: "checkmark.circle.fill")
                .foregroundStyle(.green)

            Text("In a recording's transcript, right-click a line and choose “Re-speak This Line…”. You can also ask the AI panel to replace part of a recording.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Toggle("Warn me when my camera is visible where new words are spoken", isOn: Binding(
                get: { !cameraWarningSuppressed },
                set: {
                    cameraWarningSuppressed = !$0
                    SpeechPreferences.suppressesCameraWarning = !$0
                }
            ))
            .font(.callout)

            Button("Remove the Model…", role: .destructive) { isConfirmingRemoval = true }
        }
    }

    private func failed(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(message, systemImage: "exclamationmark.triangle.fill")
                .font(.callout)
                .foregroundStyle(.orange)
                .fixedSize(horizontal: false, vertical: true)
            HStack {
                Button("Try Again") { installer.retry() }
                Button("Cancel") { installer.declineLicence(); installer.uninstall() }
            }
        }
    }
}

/// Everything the Settings item opens: the agent's connection, and Speech Replacement.
struct StudioSettingsView: View {
    @ObservedObject var speech: SpeechEngineHub

    var body: some View {
        TabView {
            AgentSettingsView()
                .tabItem { Label("Agent", systemImage: "sparkles") }
            SpeechSettingsView(installer: speech.installer)
                .tabItem { Label("Speech", systemImage: "waveform") }
        }
        .padding(8)
    }
}

/// A decision Aura needs from the user before it speaks.
struct SpeechConfirmationView: View {
    let pending: PendingSpeech
    let onProceed: (_ rememberChoice: Bool) -> Void
    let onCancel: () -> Void

    @State private var remember = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title).font(.headline)
            Text(message)
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if case .cameraWarning = pending {
                Toggle("Don't warn me again", isOn: $remember).font(.callout)
            }

            HStack {
                Spacer()
                Button("Cancel", action: onCancel)
                Button(proceedLabel) { onProceed(remember) }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(16)
        .frame(width: 400)
    }

    private var title: String {
        switch pending {
        case .cameraWarning: return "Your camera is on screen here"
        case .longHold: return "The new speech is longer than the original"
        }
    }

    private var message: String {
        switch pending {
        case .cameraWarning:
            return "The new words won't match the movement of your mouth. It works best where only your screen is showing."
        case .longHold(_, let seconds):
            return String(format: "The picture will hold on the last frame for %.0f seconds while the new speech finishes.", seconds)
        }
    }

    private var proceedLabel: String {
        switch pending {
        case .cameraWarning: return "Replace Anyway"
        case .longHold: return "Hold the Picture"
        }
    }
}
