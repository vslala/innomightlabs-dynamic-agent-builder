import Foundation

/// A stretch where the picture is magnified onto one part of the screen.
///
/// `rect` is normalized against the **visible** screen frame — what the viewer sees with no zoom,
/// which is the crop when there is one — not the source frame. That is the frame the user and the
/// agent can see, so "zoom into the top right" means what it says even after the crop changes.
struct ZoomSegment: Codable, Hashable, Identifiable, Sendable {
    var id: UUID
    /// Session time, like every time in an operation. The zoom eases in over the first
    /// `easeSeconds` of the span and out over the last.
    var span: TimeSpan
    var rect: NormalizedRect
    var easeSeconds: TimeInterval

    init(id: UUID = UUID(), span: TimeSpan, rect: NormalizedRect, easeSeconds: TimeInterval = Self.defaultEase) {
        self.id = id
        self.span = span
        self.rect = rect
        self.easeSeconds = easeSeconds
    }

    static let defaultEase: TimeInterval = 0.45
    static let easeRange: ClosedRange<TimeInterval> = 0.1...1.5
    /// Past 4x, text is unreadably soft and the move reads as a glitch rather than emphasis.
    static let maximumMagnification = 4.0
    /// Shorter than two eases there is no hold, only a wobble.
    static let minimumSpan: TimeInterval = 0.6

    var isValid: Bool {
        rect.isValidScreenCrop
            && rect.width >= 1 / Self.maximumMagnification
            && rect.height >= 1 / Self.maximumMagnification
            && span.start.isFinite && span.end.isFinite
            && span.duration >= Self.minimumSpan
            && Self.easeRange.contains(easeSeconds)
    }

    private enum CodingKeys: String, CodingKey {
        case id, start, end, rect, ease
    }

    /// Tolerant on purpose: an agent proposes `{start, end, rect}` and nothing else.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        span = TimeSpan(
            start: try container.decode(TimeInterval.self, forKey: .start),
            end: try container.decode(TimeInterval.self, forKey: .end)
        )
        rect = try container.decode(NormalizedRect.self, forKey: .rect)
        easeSeconds = try container.decodeIfPresent(TimeInterval.self, forKey: .ease) ?? Self.defaultEase
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(span.start, forKey: .start)
        try container.encode(span.end, forKey: .end)
        try container.encode(rect, forKey: .rect)
        try container.encode(easeSeconds, forKey: .ease)
    }
}

/// How the rendered cursor looks. The path it follows is recorded data and never edited.
struct CursorStyle: Codable, Hashable, Sendable {
    var visible: Bool = true
    /// Multiplies the cursor's size, which is itself a fraction of the frame height.
    var scale: Double = 1
    var ripple: Bool = true

    static let standard = CursorStyle()
    static let scaleRange: ClosedRange<Double> = 0.5...3

    var isValid: Bool { scale.isFinite && Self.scaleRange.contains(scale) }

    private enum CodingKeys: String, CodingKey { case visible, scale, ripple }

    init(visible: Bool = true, scale: Double = 1, ripple: Bool = true) {
        self.visible = visible
        self.scale = scale
        self.ripple = ripple
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        visible = try container.decodeIfPresent(Bool.self, forKey: .visible) ?? true
        scale = try container.decodeIfPresent(Double.self, forKey: .scale) ?? 1
        ripple = try container.decodeIfPresent(Bool.self, forKey: .ripple) ?? true
    }
}

/// One spoken line of a demo's voice-over, made before the take so the take could wait for it.
///
/// The clip lives beside the session (`SessionFolder.narrationClipURL`) and is derived data: the
/// text and `duration` are the whole edit, and a clip lost from disk can be spoken again.
struct NarrationLine: Codable, Hashable, Identifiable, Sendable {
    var id: UUID
    /// Session time the line starts playing.
    var at: TimeInterval
    var text: String
    /// Length of the generated clip. Zero until one has been made: an agent suggests a rewrite as
    /// a draft, and accepting it speaks the line first, so the document never describes audio
    /// that does not exist.
    var duration: TimeInterval
    /// The demo step it narrates, when it came from one. Lets a take be matched back to its spec.
    var stepID: String?

    init(id: UUID = UUID(), at: TimeInterval, text: String, duration: TimeInterval = 0, stepID: String? = nil) {
        self.id = id
        self.at = at
        self.text = text
        self.duration = duration
        self.stepID = stepID
    }

    var isDraft: Bool { duration <= 0 }
    var end: TimeInterval { at + duration }

    static let maximumDuration: TimeInterval = 120

    private enum CodingKeys: String, CodingKey { case id, at, text, duration, stepID }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        at = try container.decode(TimeInterval.self, forKey: .at)
        text = try container.decode(String.self, forKey: .text)
        duration = try container.decodeIfPresent(TimeInterval.self, forKey: .duration) ?? 0
        stepID = try container.decodeIfPresent(String.self, forKey: .stepID)
    }
}

extension SessionEdit {
    /// The visible screen frame, as the compositor will show it at no zoom. Zoom rects are
    /// normalized against this.
    static let fullFrame = NormalizedRect(x: 0, y: 0, width: 1, height: 1)
}
