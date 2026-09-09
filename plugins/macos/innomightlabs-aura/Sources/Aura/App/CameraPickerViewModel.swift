import AVFoundation
import SwiftUI

@MainActor
final class CameraPickerViewModel: ObservableObject {
    @Published private(set) var cameras: [AVCaptureDevice] = []

    @Published var selectedDeviceID: String? {
        didSet {
            let name = cameras.first { $0.uniqueID == selectedDeviceID }?.localizedName
            RecordingPreferences.lastCameraName = name
        }
    }

    func refresh() {
        cameras = CameraRecorder.availableDevices()
        if let selectedDeviceID, !cameras.contains(where: { $0.uniqueID == selectedDeviceID }) {
            self.selectedDeviceID = nil
        }
        if selectedDeviceID == nil, let savedName = RecordingPreferences.lastCameraName {
            selectedDeviceID = cameras.first { $0.localizedName == savedName }?.uniqueID
        }
    }
}
