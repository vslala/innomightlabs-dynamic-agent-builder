import AVFoundation
import SwiftUI

@MainActor
final class CameraPickerViewModel: ObservableObject {
    @Published private(set) var cameras: [AVCaptureDevice] = []
    @Published var selectedDeviceID: String?

    func refresh() {
        cameras = CameraRecorder.availableDevices()
        if let selectedDeviceID, !cameras.contains(where: { $0.uniqueID == selectedDeviceID }) {
            self.selectedDeviceID = nil
        }
    }
}
