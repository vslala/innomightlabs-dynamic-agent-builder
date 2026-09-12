import SwiftUI

/// Burned-looking subtitles drawn over the preview.
///
/// A SwiftUI overlay rather than something rendered into the composition: styling stays
/// instantly changeable, there is no compositor risk, and captions can be turned off. The
/// export writes a sidecar subtitle file instead, which is also what most editors want.
struct SubtitleOverlayView: View {
    let text: String
    /// The picture's rect within the container, so the caption stays inside the image rather
    /// than floating in the letterbox.
    let videoRect: CGRect

    /// Fraction of the picture's height to leave below the caption — the conventional safe
    /// area for burned-in subtitles.
    private let bottomInset: CGFloat = 0.09

    var body: some View {
        Text(text)
            .font(.system(size: fontSize, weight: .medium))
            .foregroundStyle(AuraTheme.textPrimary)
            .multilineTextAlignment(.center)
            .lineLimit(2)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .background {
                RoundedRectangle(cornerRadius: AuraTheme.Radius.sm)
                    .fill(Color.black.opacity(0.62))
            }
            .frame(maxWidth: videoRect.width * 0.8)
            .position(
                x: videoRect.midX,
                y: videoRect.maxY - videoRect.height * bottomInset
            )
            .allowsHitTesting(false)
    }

    /// Scaled to the picture so a caption reads the same at any window size, clamped so it
    /// stays legible when small and does not dominate when large.
    private var fontSize: CGFloat {
        min(20, max(12, videoRect.height * 0.032))
    }
}
