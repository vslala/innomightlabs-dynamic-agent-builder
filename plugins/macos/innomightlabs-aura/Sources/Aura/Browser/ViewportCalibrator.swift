import CoreGraphics
import CoreVideo
import Foundation

/// Top-left-origin window pixels, independent of window position on the desktop. Persist this
/// alongside the take; pointer events remain CSS pixels and are mapped only at the rendering edge.
struct BrowserViewportMetadata: Codable, Equatable, Sendable {
    let viewportRect: CGRect
    let viewport: BrowserViewportMetrics
    let frameSize: CGSize
    let pixelsPerCSSPixel: Double

    func windowPoint(forCSSPoint point: CGPoint) -> CGPoint {
        CGPoint(x: viewportRect.minX + point.x * pixelsPerCSSPixel,
                y: viewportRect.minY + point.y * pixelsPerCSSPixel)
    }

    func windowRect(forCSSRect rect: BrowserRect) -> CGRect {
        CGRect(x: viewportRect.minX + rect.x * pixelsPerCSSPixel,
               y: viewportRect.minY + rect.y * pixelsPerCSSPixel,
               width: rect.width * pixelsPerCSSPixel, height: rect.height * pixelsPerCSSPixel)
    }
}

enum ViewportCalibrator {
    enum CalibrationError: Error, LocalizedError, Equatable {
        case unsupportedPixelFormat, invalidCalibration, markersNotFound, inconsistentGeometry
        var errorDescription: String? {
            switch self {
            case .unsupportedPixelFormat: "Viewport calibration needs a readable BGRA screen frame."
            case .invalidCalibration: "The browser returned invalid calibration markers."
            case .markersNotFound: "Aura could not recognize the calibration markers. A Chrome popup may be covering them. Dismiss browser popups, such as Restore pages, and try again."
            case .inconsistentGeometry: "The Chrome window changed size or its calibration markers do not match. Try again."
            }
        }
    }

    /// Reads only the supplied frame. No capture, device access, or dependency on toolbar geometry.
    static func calibrate(_ frame: CVPixelBuffer, calibration: BrowserCalibration) throws -> BrowserViewportMetadata {
        guard CVPixelBufferGetPixelFormatType(frame) == kCVPixelFormatType_32BGRA,
              !CVPixelBufferIsPlanar(frame), CVPixelBufferLockBaseAddress(frame, .readOnly) == kCVReturnSuccess
        else { throw CalibrationError.unsupportedPixelFormat }
        defer { CVPixelBufferUnlockBaseAddress(frame, .readOnly) }
        guard let base = CVPixelBufferGetBaseAddress(frame) else { throw CalibrationError.unsupportedPixelFormat }
        let width = CVPixelBufferGetWidth(frame), height = CVPixelBufferGetHeight(frame)
        let stride = CVPixelBufferGetBytesPerRow(frame)
        let metrics = calibration.viewport
        guard width > 0, height > 0, stride >= width * 4,
              metrics.width.isFinite, metrics.height.isFinite, metrics.devicePixelRatio.isFinite,
              metrics.width > 32, metrics.height > 32, metrics.devicePixelRatio > 0,
              calibration.background.count == 3, calibration.markers.count == 4
        else { throw CalibrationError.invalidCalibration }
        let markers = calibration.markers
        for (index, marker) in markers.enumerated() {
            let r = marker.rect
            guard marker.color.count == 3, [r.x, r.y, r.width, r.height].allSatisfy(\.isFinite),
                  r.width > 0, r.height > 0, r.x >= 0, r.y >= 0,
                  r.x + r.width <= metrics.width, r.y + r.height <= metrics.height,
                  r.width == markers[0].rect.width, r.height == markers[0].rect.height,
                  r.x == (index % 2 == 0 ? markers[0].rect.x : metrics.width - markers[0].rect.x - r.width),
                  r.y == (index < 2 ? markers[0].rect.y : metrics.height - markers[0].rect.y - r.height),
                  !matches(marker.color, calibration.background),
                  !markers.prefix(index).contains(where: { matches($0.color, marker.color) })
            else { throw CalibrationError.invalidCalibration }
        }

        guard markers[0].rect.x + markers[0].rect.width < markers[1].rect.x,
              markers[0].rect.y + markers[0].rect.height < markers[2].rect.y else {
            throw CalibrationError.invalidCalibration
        }

        let bytes = base.assumingMemoryBound(to: UInt8.self)
        var bounds = Array(repeating: Bounds(), count: 4)
        for y in 0..<height {
            let row = bytes.advanced(by: y * stride)
            for x in 0..<width {
                let p = row.advanced(by: x * 4)
                for i in 0..<4 where matches(p, markers[i].color) {
                    bounds[i].include(x: x, y: y)
                }
            }
        }
        guard bounds.allSatisfy({ $0.count > 0 && Double($0.count) / Double($0.area) >= 0.85 }) else {
            throw CalibrationError.markersNotFound
        }
        // Native window edges can clip the viewport, so infer it from intact inset markers,
        // not from the outermost colored pixels. This also supports the original edge layout.
        let scaleX = Double(bounds[1].minX - bounds[0].minX) / (markers[1].rect.x - markers[0].rect.x)
        let scaleY = Double(bounds[2].minY - bounds[0].minY) / (markers[2].rect.y - markers[0].rect.y)
        guard scaleX.isFinite, scaleY.isFinite, scaleX > 0, scaleY > 0,
              abs(scaleX - scaleY) * max(metrics.width, metrics.height) <= 2 else {
            throw CalibrationError.inconsistentGeometry
        }
        let scale = (scaleX + scaleY) / 2
        let rect = CGRect(x: Double(bounds[0].minX) - markers[0].rect.x * scale,
                          y: Double(bounds[0].minY) - markers[0].rect.y * scale,
                          width: metrics.width * scale, height: metrics.height * scale)
        guard [rect.minX, rect.minY, rect.maxX, rect.maxY].allSatisfy(\.isFinite),
              rect.minX >= -2, rect.minY >= -2,
              rect.maxX <= Double(width) + 2, rect.maxY <= Double(height) + 2 else {
            throw CalibrationError.inconsistentGeometry
        }
        for (i, marker) in markers.enumerated() {
            let expected = CGRect(x: rect.minX + marker.rect.x * scale, y: rect.minY + marker.rect.y * scale,
                                  width: marker.rect.width * scale, height: marker.rect.height * scale)
            let actual = bounds[i].rect
            guard abs(expected.minX - actual.minX) <= 2, abs(expected.minY - actual.minY) <= 2,
                  abs(expected.maxX - actual.maxX) <= 2, abs(expected.maxY - actual.maxY) <= 2 else {
                throw CalibrationError.inconsistentGeometry
            }
        }
        // Reject a stale/partially painted calibration frame, even when all four colors exist.
        for gy in 1..<10 {
            for gx in 1..<10 {
                let x = max(0, min(width - 1, Int(rect.minX + rect.width * Double(gx) / 10)))
                let y = max(0, min(height - 1, Int(rect.minY + rect.height * Double(gy) / 10)))
                if bounds.contains(where: { $0.rect.contains(CGPoint(x: x, y: y)) }) { continue }
                guard matches(bytes.advanced(by: y * stride + x * 4), calibration.background) else {
                    throw CalibrationError.markersNotFound
                }
            }
        }
        return BrowserViewportMetadata(viewportRect: rect, viewport: metrics,
                                       frameSize: CGSize(width: width, height: height), pixelsPerCSSPixel: scale)
    }

    private static func matches(_ pixel: UnsafePointer<UInt8>, _ rgb: [UInt8]) -> Bool {
        abs(Int(pixel[2]) - Int(rgb[0])) <= 12 && abs(Int(pixel[1]) - Int(rgb[1])) <= 12
            && abs(Int(pixel[0]) - Int(rgb[2])) <= 12
    }

    private static func matches(_ a: [UInt8], _ b: [UInt8]) -> Bool {
        zip(a, b).allSatisfy { abs(Int($0) - Int($1)) <= 24 }
    }

    private struct Bounds {
        var minX = Int.max, minY = Int.max, maxX = -1, maxY = -1, count = 0
        var area: Int { (maxX - minX + 1) * (maxY - minY + 1) }
        var rect: CGRect { CGRect(x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1) }
        mutating func include(x: Int, y: Int) {
            minX = min(minX, x); minY = min(minY, y); maxX = max(maxX, x); maxY = max(maxY, y); count += 1
        }
    }
}
