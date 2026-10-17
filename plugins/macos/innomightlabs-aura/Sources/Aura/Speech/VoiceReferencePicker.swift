import Foundation

/// A stretch of the user's own speech, chosen to teach the model their voice.
///
/// Times are **microphone media time** — the transcript's own clock — because that is where the
/// audio is read from.
struct VoiceReference: Equatable, Sendable {
    let start: TimeInterval
    let end: TimeInterval
    /// What is said in it, which the model needs alongside the audio.
    let text: String

    var duration: TimeInterval { end - start }
}

/// Finds the best 6–10 seconds of clean, continuous speech in a recording.
///
/// The model clones whatever it is given, flaws included: a reference with an "um" in it makes
/// every sentence hesitate, and a reference whose transcript is wrong makes it mispronounce. So
/// this prefers speech that is fluent, without fillers or long pauses, at a believable pace
/// (a pace far from natural usually means the transcript's timing is off), and ending where a
/// sentence does.
enum VoiceReferencePicker {
    static let minimumDuration: TimeInterval = 6
    static let maximumDuration: TimeInterval = 10
    private static let idealDuration: TimeInterval = 8
    /// A pause this long inside the clip is a breath for effect, not fluent speech.
    private static let longestPause: TimeInterval = 0.6
    private static let wordsPerSecond: ClosedRange<Double> = 1.5...4.5
    private static let fillers: Set<String> = ["um", "uh", "erm", "er", "ah", "hmm", "mm", "uhm", "umm"]

    /// - Parameters:
    ///   - words: the transcript's words, in microphone media time.
    ///   - unusable: stretches that must not appear in the reference, in the same clock — what
    ///     has been cut, and what has already been replaced by synthesized speech.
    static func pick(words: [Transcript.Word], avoiding unusable: [TimeSpan] = []) -> VoiceReference? {
        let words = words.sorted { $0.start < $1.start }
        var best: (reference: VoiceReference, score: Double)?

        for first in words.indices {
            guard !isUnfit(words[first], unusable) else { continue }
            var last = first

            while last < words.count {
                let word = words[last]
                if last > first {
                    if isUnfit(word, unusable) { break }
                    // A pause that long ends the run: nothing after it can be in this clip.
                    if word.start - words[last - 1].end > longestPause { break }
                }

                let duration = word.end - words[first].start
                if duration > maximumDuration { break }
                if duration >= minimumDuration,
                   let candidate = candidate(words[first...last], duration: duration),
                   best == nil || candidate.score > best!.score {
                    best = candidate
                }
                last += 1
            }
        }
        return best?.reference
    }

    private static func candidate(
        _ run: ArraySlice<Transcript.Word>,
        duration: TimeInterval
    ) -> (reference: VoiceReference, score: Double)? {
        let rate = Double(run.count) / duration
        guard wordsPerSecond.contains(rate) else { return nil }

        let text = run.map { $0.text.trimmingCharacters(in: .whitespaces) }.joined(separator: " ")
        // Ending where a sentence ends is worth more than a second of length.
        let endsCleanly = text.last.map { ".!?".contains($0) } ?? false
        let score = -abs(duration - idealDuration) + (endsCleanly ? 1.5 : 0)

        return (VoiceReference(start: run.first!.start, end: run.last!.end, text: text), score)
    }

    private static func isUnfit(_ word: Transcript.Word, _ unusable: [TimeSpan]) -> Bool {
        let bare = word.text.lowercased().trimmingCharacters(in: .punctuationCharacters.union(.whitespaces))
        if fillers.contains(bare) { return true }
        return unusable.contains { $0.start < word.end && word.start < $0.end }
    }
}
