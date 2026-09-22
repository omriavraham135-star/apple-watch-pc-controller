import Foundation
import Observation

/// Everything the watch knows about the PC.
///
/// One client owns all the talking, so the views only read state and call
/// intents. Requests are deliberately short-lived: on a wrist, a request that
/// hangs for thirty seconds is worse than one that fails fast and says so.
@Observable
final class PCClient {

    // MARK: - State the views read

    var isConnected = false
    var volume: Int = 50
    var isMuted = false

    var powerActions: [PowerAction] = []
    var shortcuts: [Shortcut] = []
    var shortcutStatus: [String: Bool] = [:]
    var stats: MachineStats?

    var lastMessage: String = ""

    /// Where the PC lives. Empty until the user fills it in on the settings screen.
    var host: String {
        didSet { UserDefaults.standard.set(host, forKey: Self.hostKey) }
    }

    static let hostKey = "pc_ip_address"

    private let session: URLSession

    init() {
        self.host = UserDefaults.standard.string(forKey: Self.hostKey) ?? ""

        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 4
        config.waitsForConnectivity = false
        self.session = URLSession(configuration: config)
    }

    var isConfigured: Bool { !host.trimmingCharacters(in: .whitespaces).isEmpty }

    // MARK: - Plumbing

    private func url(_ path: String) -> URL? {
        let clean = host.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return nil }
        return URL(string: "http://\(clean):8000\(path)")
    }

    private func get<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        guard let url = url(path) else { throw PCError.notConfigured }
        let (data, response) = try await session.data(from: url)
        try Self.check(response)
        return try JSONDecoder().decode(T.self, from: data)
    }

    @discardableResult
    private func post<T: Decodable>(
        _ path: String,
        body: [String: Any]? = nil,
        as type: T.Type
    ) async throws -> T {
        guard let url = url(path) else { throw PCError.notConfigured }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }

        let (data, response) = try await session.data(for: request)
        try Self.check(response)
        return try JSONDecoder().decode(T.self, from: data)
    }

    private static func check(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200..<300).contains(http.statusCode) else {
            throw PCError.http(http.statusCode)
        }
    }

    // MARK: - Reading

    /// Volume, mute and reachability. Cheap enough to poll while a screen is up.
    @MainActor
    func refreshStatus() async {
        do {
            let status = try await get("/api/status", as: StatusResponse.self)
            volume = status.volume
            isMuted = status.isMuted
            isConnected = true
        } catch {
            isConnected = false
        }
    }

    @MainActor
    func refreshStats() async {
        stats = try? await get("/api/stats", as: MachineStats.self)
    }

    /// The fixed lists. Fetched once when the app opens.
    @MainActor
    func loadDefinitions() async {
        if let power = try? await get("/api/power", as: PowerListResponse.self) {
            powerActions = power.actions
        }
        if let list = try? await get("/api/actions", as: ShortcutListResponse.self) {
            shortcuts = list.actions
        }
    }

    /// Which shortcut apps are open. Apps come and go on a human timescale,
    /// so this is polled gently.
    @MainActor
    func refreshShortcutStatus() async {
        guard let body = try? await get("/api/actions/status", as: ShortcutStatusResponse.self)
        else { return }
        shortcutStatus = body.statuses.mapValues(\.running)
    }

    // MARK: - Acting

    @MainActor
    func setVolume(_ value: Int) async {
        let clamped = max(0, min(100, value))
        volume = clamped  // optimistic: the slider must not lag the finger
        do {
            let result = try await post("/api/volume", body: ["volume": clamped], as: VolumeResponse.self)
            volume = result.volume
        } catch {
            isConnected = false
        }
    }

    @MainActor
    func send(command text: String) async -> CommandOutcome {
        do {
            let result = try await post("/api/command", body: ["text": text], as: CommandResponse.self)
            if let newVolume = result.details?.newVolume { volume = newVolume }
            if let muted = result.details?.isMuted { isMuted = muted }
            lastMessage = result.feedback
            isConnected = true
            return result.status == "success" ? .understood(result.feedback) : .notUnderstood(result.feedback)
        } catch {
            isConnected = false
            lastMessage = "אין קשר למחשב"
            return .failed
        }
    }

    @MainActor
    func run(power action: String) async -> Bool {
        do {
            _ = try await post("/api/power", body: ["action": action], as: GenericResponse.self)
            return true
        } catch {
            isConnected = false
            return false
        }
    }

    @MainActor
    func run(shortcut id: String) async -> ShortcutOutcome {
        guard let encoded = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)
        else { return .failed }
        do {
            let result = try await post("/api/actions/\(encoded)", body: nil, as: ShortcutRunResponse.self)
            return result.details.status == "focused" ? .raised : .launched
        } catch {
            isConnected = false
            return .failed
        }
    }
}

enum PCError: Error {
    case notConfigured
    case http(Int)
}

enum CommandOutcome {
    case understood(String)
    case notUnderstood(String)
    case failed
}

enum ShortcutOutcome {
    case launched
    case raised
    case failed
}
