import AVFoundation
import SwiftUI

@MainActor
final class MicrophonePickerViewModel: ObservableObject {
    @Published private(set) var microphones: [AVCaptureDevice] = []

    @Published var selectedDeviceID: String? {
        didSet {
            let name = microphones.first { $0.uniqueID == selectedDeviceID }?.localizedName
            RecordingPreferences.lastMicrophoneName = name
        }
    }

    func refresh() {
        microphones = MicrophoneCaptureSource.availableDevices()
        if let selectedDeviceID, !microphones.contains(where: { $0.uniqueID == selectedDeviceID }) {
            self.selectedDeviceID = nil
        }
        if selectedDeviceID == nil, let savedName = RecordingPreferences.lastMicrophoneName {
            selectedDeviceID = microphones.first { $0.localizedName == savedName }?.uniqueID
        }
    }
}
