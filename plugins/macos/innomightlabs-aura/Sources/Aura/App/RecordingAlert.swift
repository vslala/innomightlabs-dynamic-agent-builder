import UserNotifications

/// A system notification for problems found mid-recording.
///
/// The menu bar popover is closed for nearly all of a take, so a warning shown only there is a
/// warning nobody reads until the take is already lost. Permission is asked the first time an
/// alert is needed rather than at launch: most sessions never need one, and a prompt with no
/// visible reason behind it is one users decline.
enum RecordingAlert {
    static func post(title: String, body: String) {
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else { return }
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = body
            content.sound = .default
            center.add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
        }
    }
}
