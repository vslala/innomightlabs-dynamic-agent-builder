import SwiftUI

extension Color {
    /// Builds a colour from a `0xRRGGBB` literal, so the design tokens read the same as the
    /// spec they came from.
    init(hex: UInt32, opacity: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: opacity
        )
    }
}
