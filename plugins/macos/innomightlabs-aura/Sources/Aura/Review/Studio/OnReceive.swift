import Combine
import SwiftUI

extension View {
    /// Runs `action` when a notification is posted. A thin wrapper so views can subscribe
    /// without each one restating the publisher plumbing.
    func onReceive(_ name: Notification.Name, perform action: @escaping () -> Void) -> some View {
        onReceive(NotificationCenter.default.publisher(for: name)) { _ in action() }
    }
}
