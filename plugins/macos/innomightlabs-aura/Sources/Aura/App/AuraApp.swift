import SwiftUI

@main
struct AuraApp: App {
    @StateObject private var recordingController = RecordingController()

    var body: some Scene {
        MenuBarExtra("Aura", systemImage: "waveform") {
            MenuBarContentView(controller: recordingController)
        }
    }
}
