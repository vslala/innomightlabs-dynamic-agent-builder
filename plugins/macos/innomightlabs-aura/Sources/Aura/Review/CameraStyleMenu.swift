import SwiftUI

/// Shape, border, and shadow for the camera overlay.
///
/// Unlike position, the style applies to the whole recording rather than being keyframed:
/// a camera that changes shape partway through reads as a glitch, not an edit.
struct CameraStyleMenu: View {
    @ObservedObject var viewModel: ReviewViewModel

    var body: some View {
        let style = viewModel.cameraStyle

        return Menu {
            Picker("Shape", selection: Binding(
                get: { style.shape },
                set: { viewModel.setCameraShape($0) }
            )) {
                Text("Rectangle").tag(PiPStyle.Shape.rectangle)
                Text("Rounded").tag(PiPStyle.Shape.rounded)
                Text("Circle").tag(PiPStyle.Shape.circle)
            }
            .pickerStyle(.inline)

            Divider()

            Toggle("Border", isOn: Binding(
                get: { style.borderWidth > 0 },
                set: { on in
                    var updated = style
                    updated.borderWidth = on ? 0.02 : 0
                    viewModel.setCameraStyle(updated)
                }
            ))

            Toggle("Shadow", isOn: Binding(
                get: { style.shadowOpacity > 0 },
                set: { on in
                    var updated = style
                    updated.shadowOpacity = on ? 0.5 : 0
                    updated.shadowRadius = on ? 0.06 : 0
                    viewModel.setCameraStyle(updated)
                }
            ))
        } label: {
            Label("Camera Style", systemImage: icon(for: style.shape))
        }
        .help(style.isPlainRectangle
              ? "Shape, border, and shadow"
              : "Styled overlays render through the Core Image compositor")
    }

    private func icon(for shape: PiPStyle.Shape) -> String {
        switch shape {
        case .rectangle: return "rectangle"
        case .rounded: return "rectangle.roundedtop"
        case .circle: return "circle"
        }
    }
}
