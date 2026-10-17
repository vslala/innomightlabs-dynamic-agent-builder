import Foundation

/// Pure conversion at the boundary between recorded browser metadata and ordinary edits.
enum BrowserViewportCropSeed {
    static func operation(viewport: BrowserViewportMetadata) -> EditOperation? {
        let frame = viewport.frameSize
        let rect = viewport.viewportRect
        guard frame.width.isFinite, frame.height.isFinite, frame.width > 0, frame.height > 0,
              rect.origin.x.isFinite, rect.origin.y.isFinite,
              rect.width.isFinite, rect.height.isFinite, rect.width > 0, rect.height > 0 else { return nil }
        let crop = NormalizedRect(x: rect.origin.x / frame.width, y: rect.origin.y / frame.height,
                                  width: rect.width / frame.width, height: rect.height / frame.height)
        guard crop.isValidScreenCrop else { return nil }
        return .setScreenCrop(crop)
    }
}

extension EditDocumentStore {
    /// Called before review subscribes to document changes. The marker is not an effect and
    /// deliberately precedes the undo snapshot: undo removes the crop, not the fact we seeded.
    @MainActor
    func seedBrowserViewport(from url: URL) {
        guard !document.hasSeededBrowserViewport,
              let data = try? Data(contentsOf: url),
              let viewport = try? JSONDecoder().decode(BrowserViewportMetadata.self, from: data),
              let operation = BrowserViewportCropSeed.operation(viewport: viewport) else { return }
        repair {
            $0.hasSeededBrowserViewport = true
            return true
        }
        // Never replace an existing user-authored crop.
        if document.screenCrop == nil { apply(operation) }
    }
}
