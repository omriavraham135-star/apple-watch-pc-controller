import Foundation

// The server speaks snake_case; these mirror it exactly so there is one place
// to look when an endpoint changes.

struct StatusResponse: Decodable {
    let status: String
    let volume: Int
    let isMuted: Bool
    let localIP: String

    enum CodingKeys: String, CodingKey {
        case status, volume
        case isMuted = "is_muted"
        case localIP = "local_ip"
    }
}

struct VolumeResponse: Decodable {
    let volume: Int
}

struct GenericResponse: Decodable {
    let status: String
}

// MARK: - Voice commands

struct CommandResponse: Decodable {
    let status: String
    let feedback: String
    let details: CommandDetails?
}

struct CommandDetails: Decodable {
    let newVolume: Int?
    let isMuted: Bool?

    enum CodingKeys: String, CodingKey {
        case newVolume = "new_volume"
        case isMuted = "is_muted"
    }
}

// MARK: - Power

struct PowerListResponse: Decodable {
    let actions: [PowerAction]
}

struct PowerAction: Decodable, Identifiable, Hashable {
    let action: String
    let label: String
    let destructive: Bool
    /// How long the tile must be held before this fires. Zero means a plain tap.
    let holdSeconds: Double

    var id: String { action }

    enum CodingKeys: String, CodingKey {
        case action, label, destructive
        case holdSeconds = "hold_seconds"
    }
}

// MARK: - Machine vitals

struct MachineStats: Decodable {
    let cpu: Int
    let memory: Int
    let disk: Int
    let memoryUsedGB: Double
    let memoryTotalGB: Double
    let diskFreeGB: Double
    let diskTotalGB: Double
    let uptimeSeconds: Int

    enum CodingKeys: String, CodingKey {
        case cpu, memory, disk
        case memoryUsedGB = "memory_used_gb"
        case memoryTotalGB = "memory_total_gb"
        case diskFreeGB = "disk_free_gb"
        case diskTotalGB = "disk_total_gb"
        case uptimeSeconds = "uptime_seconds"
    }
}

// MARK: - Shortcuts

struct ShortcutListResponse: Decodable {
    let actions: [Shortcut]
}

struct Shortcut: Decodable, Identifiable, Hashable {
    let id: String
    let label: String
    let icon: String
    /// The executable this shortcut watches, if any. Present means the tile can
    /// show whether the app is already open.
    let process: String?
}

struct ShortcutStatusResponse: Decodable {
    let statuses: [String: ShortcutState]
}

struct ShortcutState: Decodable {
    let running: Bool
    let pid: Int?
}

struct ShortcutRunResponse: Decodable {
    let status: String
    let details: ShortcutRunDetails
}

struct ShortcutRunDetails: Decodable {
    let id: String
    let label: String
    /// "launched" when the app was started, "focused" when an open window was raised.
    let status: String
}
