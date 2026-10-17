import Foundation

/// Fetches one file. A protocol only because downloading hundreds of megabytes is not something
/// a test should do; `URLSessionDownloader` is the real one.
protocol FileDownloading: Sendable {
    /// Downloads `url` to `destination`, replacing anything there.
    /// - Parameter progress: total bytes received so far for this file.
    func download(_ url: URL, to destination: URL, progress: @escaping @Sendable (Int64) -> Void) async throws
}

struct URLSessionDownloader: FileDownloading {
    func download(_ url: URL, to destination: URL, progress: @escaping @Sendable (Int64) -> Void) async throws {
        let transfer = Transfer(destination: destination, progress: progress)
        let session = URLSession(configuration: .default, delegate: transfer, delegateQueue: nil)
        defer { session.finishTasksAndInvalidate() }

        let task = session.downloadTask(with: url)
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                transfer.begin(continuation)
                task.resume()
            }
        } onCancel: {
            task.cancel()
        }
    }

    /// One download's delegate. The file has to be moved inside `didFinishDownloadingTo`,
    /// because URLSession deletes it as soon as that returns.
    private final class Transfer: NSObject, URLSessionDownloadDelegate, @unchecked Sendable {
        private let destination: URL
        private let progress: @Sendable (Int64) -> Void
        private let lock = NSLock()
        private var continuation: CheckedContinuation<Void, Error>?
        private var moveError: Error?

        init(destination: URL, progress: @escaping @Sendable (Int64) -> Void) {
            self.destination = destination
            self.progress = progress
        }

        func begin(_ continuation: CheckedContinuation<Void, Error>) {
            lock.withLock { self.continuation = continuation }
        }

        func urlSession(
            _ session: URLSession, downloadTask: URLSessionDownloadTask,
            didWriteData bytesWritten: Int64, totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64
        ) {
            progress(totalBytesWritten)
        }

        func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
            if let http = downloadTask.response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                lock.withLock { moveError = DownloadError.badStatus(http.statusCode) }
                return
            }
            do {
                try? FileManager.default.removeItem(at: destination)
                try FileManager.default.moveItem(at: location, to: destination)
            } catch {
                lock.withLock { moveError = error }
            }
        }

        func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
            let (continuation, failure) = lock.withLock { (self.continuation, moveError) }
            self.lock.withLock { self.continuation = nil }
            if let error = error ?? failure {
                continuation?.resume(throwing: (error as? URLError)?.code == .cancelled ? CancellationError() : error)
            } else {
                continuation?.resume()
            }
        }
    }

    enum DownloadError: Error, LocalizedError {
        case badStatus(Int)

        var errorDescription: String? {
            switch self {
            case .badStatus(let code): return "The download was refused (HTTP \(code))."
            }
        }
    }
}
