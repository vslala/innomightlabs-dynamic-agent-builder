import XCTest
import CoreVideo
@testable import Aura

final class ViewportCalibratorTests: XCTestCase {
    private func calibration(inset: Double = 32) -> BrowserCalibration {
        let colors: [[UInt8]] = [[255, 0, 64], [0, 255, 64], [64, 0, 255], [255, 224, 0]]
        return BrowserCalibration(viewport: .init(width: 200, height: 120, devicePixelRatio: 2),
                                  background: [32, 48, 64], markers: colors.enumerated().map { i, color in
            .init(rect: .init(x: i % 2 == 0 ? inset : 184 - inset,
                             y: i < 2 ? inset : 104 - inset, width: 16, height: 16), color: color)
        })
    }

    private func frame(scale: Double = 2, omit: Int? = nil, extraMarker: Bool = false,
                       wrongBackground: Bool = false, noise: Int = 0,
                       paintedCalibration: BrowserCalibration? = nil, clippedEdges: Bool = false,
                       sparseMarkers: Bool = false, verticalScale: Double? = nil,
                       origin: CGPoint = CGPoint(x: 10, y: 40)) throws -> CVPixelBuffer {
        let calibration = paintedCalibration ?? calibration(), width = Int(220 * scale), height = Int(170 * scale)
        var buffer: CVPixelBuffer?
        let status = CVPixelBufferCreate(kCFAllocatorDefault, width, height, kCVPixelFormatType_32BGRA,
                                        [kCVPixelBufferBytesPerRowAlignmentKey: 256] as CFDictionary, &buffer)
        XCTAssertEqual(status, kCVReturnSuccess)
        let result = try XCTUnwrap(buffer)
        CVPixelBufferLockBaseAddress(result, [])
        defer { CVPixelBufferUnlockBaseAddress(result, []) }
        let bytes = try XCTUnwrap(CVPixelBufferGetBaseAddress(result)).assumingMemoryBound(to: UInt8.self)
        let stride = CVPixelBufferGetBytesPerRow(result)
        for y in 0..<height {
            for x in 0..<width {
                let cssX = Double(x) / scale - origin.x, cssY = Double(y) / (verticalScale ?? scale) - origin.y
                var color: [UInt8] = [90, 90, 90]
                if cssX >= 0, cssX < 200, cssY >= 0, cssY < 120 {
                    color = wrongBackground ? [70, 70, 70] : calibration.background
                    for (i, marker) in calibration.markers.enumerated() where omit != i {
                        if cssX >= marker.rect.x, cssX < marker.rect.x + marker.rect.width,
                           cssY >= marker.rect.y, cssY < marker.rect.y + marker.rect.height,
                           !sparseMarkers || (x + y) % 2 == 0 { color = marker.color }
                    }
                }
                if clippedEdges, cssX >= 0, cssX < 200, cssY >= 0, cssY < 120 {
                    let cornerX = min(cssX, 200 - cssX), cornerY = min(cssY, 120 - cssY)
                    if cssY < 5 || (cornerX < 12 && cornerY < 12 && hypot(cornerX - 12, cornerY - 12) > 12) {
                        color = [90, 90, 90]
                    }
                }
                if extraMarker, x < 4, y < 4 { color = calibration.markers[0].color }
                let p = bytes.advanced(by: y * stride + x * 4)
                p[0] = UInt8(clamping: Int(color[2]) + noise)
                p[1] = UInt8(clamping: Int(color[1]) + noise)
                p[2] = UInt8(clamping: Int(color[0]) + noise); p[3] = 255
            }
        }
        return result
    }

    func testRetinaFrameFindsViewportBelowToolbarAndMapsCSS() throws {
        let metadata = try ViewportCalibrator.calibrate(frame(), calibration: calibration())
        XCTAssertEqual(metadata.viewportRect, CGRect(x: 20, y: 80, width: 400, height: 240))
        XCTAssertEqual(metadata.windowPoint(forCSSPoint: CGPoint(x: 50, y: 25)), CGPoint(x: 120, y: 130))
        XCTAssertEqual(metadata.windowRect(forCSSRect: .init(x: 10, y: 10, width: 30, height: 20)),
                       CGRect(x: 40, y: 100, width: 60, height: 40))
        XCTAssertEqual(metadata.frameSize, CGSize(width: 440, height: 340))
        XCTAssertEqual(try JSONDecoder().decode(BrowserViewportMetadata.self, from: JSONEncoder().encode(metadata)), metadata)
    }

    func testMappingUsesCapturedScaleNotAssumedDPRAndToleratesColorRounding() throws {
        for scale in [1.0, 1.5, 2.0] {
            let metadata = try ViewportCalibrator.calibrate(frame(scale: scale, noise: 5), calibration: calibration())
            XCTAssertEqual(metadata.pixelsPerCSSPixel, scale, accuracy: 0.001)
            XCTAssertEqual(metadata.viewport.devicePixelRatio, 2)
        }
    }

    func testMissingMarkerDuplicateColorAndWrongBackgroundAreRejected() throws {
        XCTAssertThrowsError(try ViewportCalibrator.calibrate(frame(omit: 3), calibration: calibration()))
        XCTAssertThrowsError(try ViewportCalibrator.calibrate(frame(extraMarker: true), calibration: calibration()))
        XCTAssertThrowsError(try ViewportCalibrator.calibrate(frame(wrongBackground: true), calibration: calibration()))
    }

    func testInvalidHostGeometryAndColorsAreRejected() throws {
        var bad = calibration()
        bad.markers[0].color = []
        XCTAssertThrowsError(try ViewportCalibrator.calibrate(frame(), calibration: bad))
        bad = calibration(); bad.viewport.width = .nan
        XCTAssertThrowsError(try ViewportCalibrator.calibrate(frame(), calibration: bad))
        bad = calibration(); bad.markers[3].rect.x -= 1
        XCTAssertThrowsError(try ViewportCalibrator.calibrate(frame(), calibration: bad))
        bad = calibration(); bad.markers[1].color = bad.markers[0].color
        XCTAssertThrowsError(try ViewportCalibrator.calibrate(frame(), calibration: bad))
    }

    func testInsetMarkersSurviveClippedTopAndRoundedViewportCornersAtOneAndTwoTimes() throws {
        for scale in [1.0, 2.0] {
            let metadata = try ViewportCalibrator.calibrate(frame(scale: scale, noise: 5, clippedEdges: true),
                                                          calibration: calibration())
            XCTAssertEqual(metadata.viewportRect, CGRect(x: 10 * scale, y: 40 * scale,
                                                        width: 200 * scale, height: 120 * scale))
            for point in [CGPoint.zero, CGPoint(x: 200, y: 120), CGPoint(x: 73, y: 49)] {
                let mapped = metadata.windowPoint(forCSSPoint: point)
                XCTAssertEqual(mapped.x, (10 + point.x) * scale, accuracy: 2)
                XCTAssertEqual(mapped.y, (40 + point.y) * scale, accuracy: 2)
            }
        }
    }

    func testSymmetricLayoutsIncludeLegacyEdgeAndOtherInsets() throws {
        for inset in [0.0, 12.0, 32.0] {
            let layout = calibration(inset: inset)
            for scale in [1.0, 1.3, 2.0] {
                let metadata = try ViewportCalibrator.calibrate(frame(scale: scale, paintedCalibration: layout),
                                                              calibration: layout)
                for point in [CGPoint.zero, CGPoint(x: 200, y: 120)] {
                    let mapped = metadata.windowPoint(forCSSPoint: point)
                    XCTAssertEqual(mapped.x, (10 + point.x) * scale, accuracy: 2)
                    XCTAssertEqual(mapped.y, (40 + point.y) * scale, accuracy: 2)
                }
            }
        }
    }

    func testMalformedMarkerSizesOffsetsAndSparseColorsFailAtOneAndTwoTimes() throws {
        for scale in [1.0, 2.0] {
            for index in 0..<4 {
                var painted = calibration()
                painted.markers[index].rect.width -= 4
                XCTAssertThrowsError(try ViewportCalibrator.calibrate(
                    frame(scale: scale, paintedCalibration: painted), calibration: calibration()))
                painted = calibration()
                painted.markers[index].rect.y += 6
                XCTAssertThrowsError(try ViewportCalibrator.calibrate(
                    frame(scale: scale, paintedCalibration: painted), calibration: calibration()))
            }
            XCTAssertThrowsError(try ViewportCalibrator.calibrate(frame(scale: scale, sparseMarkers: true),
                                                                calibration: calibration()))
            XCTAssertThrowsError(try ViewportCalibrator.calibrate(frame(scale: scale, verticalScale: scale * 1.1),
                                                                calibration: calibration()))
        }
    }

    func testExtrapolatedViewportMustFitCaptureAndMarkerLayoutMustNotOverlap() throws {
        XCTAssertThrowsError(try ViewportCalibrator.calibrate(frame(origin: CGPoint(x: -10, y: 40)),
                                                            calibration: calibration()))
        XCTAssertThrowsError(try ViewportCalibrator.calibrate(frame(origin: CGPoint(x: 30, y: 40)),
                                                            calibration: calibration()))
        var bad = calibration(inset: 52)
        XCTAssertThrowsError(try ViewportCalibrator.calibrate(frame(), calibration: bad))
        bad = calibration(); bad.markers[1].rect.width = 12
        XCTAssertThrowsError(try ViewportCalibrator.calibrate(frame(), calibration: bad))
    }

    func testDisplayTransformedColorsAreNotAcceptedByWideningColorTolerance() throws {
        var painted = calibration()
        painted.markers[0].color = [208, 75, 71]
        XCTAssertThrowsError(try ViewportCalibrator.calibrate(frame(paintedCalibration: painted),
                                                            calibration: calibration())) {
            XCTAssertEqual($0 as? ViewportCalibrator.CalibrationError, .markersNotFound)
        }
    }

    func testUnsupportedPixelFormatFailsClearly() throws {
        var buffer: CVPixelBuffer?
        XCTAssertEqual(CVPixelBufferCreate(kCFAllocatorDefault, 20, 20, kCVPixelFormatType_32ARGB, nil, &buffer), kCVReturnSuccess)
        XCTAssertThrowsError(try ViewportCalibrator.calibrate(XCTUnwrap(buffer), calibration: calibration())) {
            XCTAssertEqual($0 as? ViewportCalibrator.CalibrationError, .unsupportedPixelFormat)
        }
    }
}
