import SwiftUI

/// The studio design system: dark, low-noise, one accent.
///
/// Deliberately flat values rather than semantic `Color` assets. The window forces dark
/// appearance, so there is no light variant to resolve against — and these exact values were
/// chosen against a dark ground.
enum AuraTheme {
    // MARK: - Surfaces

    static let background = Color(hex: 0x0B0D12)
    static let surface = Color(hex: 0x12151C)
    static let surfaceElevated = Color(hex: 0x181C25)

    /// Used sparingly. Hierarchy comes from elevation and spacing; a border is for the few
    /// places where two surfaces of the same elevation genuinely meet.
    static let border = Color.white.opacity(0.08)

    // MARK: - Text

    static let textPrimary = Color(hex: 0xF5F7FA)
    static let textSecondary = Color(hex: 0x9CA3AF)
    /// For disabled affordances — present so the user can see what exists, quiet enough to
    /// read as unavailable.
    static let textTertiary = Color(hex: 0x9CA3AF, opacity: 0.45)

    // MARK: - Accent

    /// The only accent. Reserved for what genuinely wants attention: the primary action, the
    /// active nav item, the playhead, the selection.
    static let accent = Color(hex: 0x7C5CFC)
    static let accentHover = Color(hex: 0x8B6CFF)
    static let danger = Color(hex: 0xEF4444)

    /// A tinted fill for accent-bearing surfaces. Flat opacity, never a gradient.
    static func accentFill(_ opacity: Double = 0.14) -> Color {
        Color(hex: 0x7C5CFC, opacity: opacity)
    }

    // MARK: - Metrics

    /// 8px system. Named rather than numeric at call sites so spacing stays consistent.
    enum Space {
        static let xs: CGFloat = 4
        static let sm: CGFloat = 8
        static let md: CGFloat = 16
        static let lg: CGFloat = 24
        static let xl: CGFloat = 32
    }

    enum Radius {
        static let sm: CGFloat = 8
        static let md: CGFloat = 10
        static let lg: CGFloat = 12
    }

    /// The timeline's share of window height, and the bounds it is clamped to.
    ///
    /// A fraction rather than a fixed height so the preview keeps the majority of the area at
    /// any window size, clamped so it stays usable on a small window and does not sprawl on a
    /// large one.
    enum Timeline {
        static let heightFraction: CGFloat = 0.32
        static let minHeight: CGFloat = 220
        static let maxHeight: CGFloat = 420

        static func height(forWindowHeight total: CGFloat) -> CGFloat {
            min(maxHeight, max(minHeight, total * heightFraction))
        }
    }

    /// Leading inset the header must reserve for the traffic lights, which float over it once
    /// the titlebar is transparent.
    static let trafficLightInset: CGFloat = 78
}
