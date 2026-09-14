import XCTest
import AVFoundation
@testable import Aura

final class ExportFormatTests: XCTestCase {
    private func probe(_ kind: TrackKind, displaySize: CGSize? = CGSize(width: 1920, height: 1080)) -> SourceTrackProbe {
        SourceTrackProbe(
            url: URL(fileURLWithPath: "/tmp/aura-tests/\(kind.rawValue)"),
            kind: kind,
            duration: Timeline.time(seconds: 30),
            displaySize: kind.isVideo ? displaySize : nil,
            preferredTransform: .identity
        )
    }

    func testAudioFormatWhenTheTimelineHasNoBaseLayer() {
        let resolved = TimelineResolver.resolve(document: .initial(duration: 30), probes: [probe(.microphone)])
        XCTAssertEqual(ExportFormat(timeline: resolved), .audio)
    }

    func testVideoFormatWhenTheTimelineHasABaseLayer() {
        let resolved = TimelineResolver.resolve(document: .initial(duration: 30), probes: [probe(.screen)])
        XCTAssertEqual(ExportFormat(timeline: resolved), .video)
    }

    func testFileExtensions() {
        XCTAssertEqual(ExportFormat.video.fileExtension, "mp4")
        XCTAssertEqual(ExportFormat.audio.fileExtension, "m4a")
    }

    func testContentTypes() {
        XCTAssertEqual(ExportFormat.video.contentType, .mpeg4Movie)
        XCTAssertEqual(ExportFormat.audio.contentType, .mpeg4Audio)
    }

    func testFileTypes() {
        XCTAssertEqual(ExportFormat.video.fileType, .mp4)
        XCTAssertEqual(ExportFormat.audio.fileType, .m4a)
    }
}
