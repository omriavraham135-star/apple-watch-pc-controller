import SwiftUI

/// What the orb is doing. Each state is a colour *and* a tempo — the motion
/// carries as much of the meaning as the hue, which matters on a screen this
/// small and at this glance length.
enum OrbState {
    case idle
    case listening
    case thinking
    case success
    case error

    var configuration: OrbConfiguration {
        switch self {
        case .idle:
            OrbConfiguration(
                backgroundColors: [
                    Color(red: 0.06, green: 0.11, blue: 0.31),
                    Color(red: 0.23, green: 0.36, blue: 0.86),
                    Color(red: 0.37, green: 0.36, blue: 0.90),
                ],
                glowColor: Color(red: 0.55, green: 0.70, blue: 1.0),
                coreGlowIntensity: 0.8,
                speed: 34
            )
        case .listening:
            OrbConfiguration(
                backgroundColors: [
                    Color(red: 0.02, green: 0.24, blue: 0.39),
                    Color(red: 0.04, green: 0.52, blue: 1.00),
                    Color(red: 0.42, green: 0.94, blue: 1.00),
                ],
                glowColor: Color(red: 0.66, green: 0.96, blue: 1.0),
                coreGlowIntensity: 1.2,
                speed: 95
            )
        case .thinking:
            OrbConfiguration(
                backgroundColors: [
                    Color(red: 0.18, green: 0.06, blue: 0.34),
                    Color(red: 0.55, green: 0.23, blue: 0.92),
                    Color(red: 0.84, green: 0.62, blue: 1.00),
                ],
                glowColor: Color(red: 0.89, green: 0.73, blue: 1.0),
                coreGlowIntensity: 1.1,
                speed: 150
            )
        case .success:
            OrbConfiguration(
                backgroundColors: [
                    Color(red: 0.02, green: 0.25, blue: 0.17),
                    Color(red: 0.07, green: 0.66, blue: 0.44),
                    Color(red: 0.28, green: 0.88, blue: 0.55),
                ],
                glowColor: Color(red: 0.65, green: 1.0, blue: 0.80),
                coreGlowIntensity: 1.15,
                speed: 60
            )
        case .error:
            OrbConfiguration(
                backgroundColors: [
                    Color(red: 0.27, green: 0.06, blue: 0.03),
                    Color(red: 0.88, green: 0.22, blue: 0.17),
                    Color(red: 1.00, green: 0.42, blue: 0.30),
                ],
                glowColor: Color(red: 1.0, green: 0.72, blue: 0.65),
                coreGlowIntensity: 1.0,
                speed: 80
            )
        }
    }
}

@main
struct PCVolumeWatchApp: App {
    @State private var pc = PCClient()

    var body: some Scene {
        WindowGroup {
            RootView(pc: pc)
        }
    }
}

struct RootView: View {
    @Bindable var pc: PCClient

    @State private var page = RootView.requestedStartPage
    @State private var orbState: OrbState = .idle

    /// Lets the screenshot job open one page directly. The argument is absent
    /// in normal use, so this is zero behaviour change on a real watch.
    static var requestedStartPage: Int {
        let args = ProcessInfo.processInfo.arguments
        guard let i = args.firstIndex(of: "-startPage"),
              i + 1 < args.count,
              let page = Int(args[i + 1]),
              (0...3).contains(page)
        else { return 0 }
        return page
    }

    var body: some View {
        NavigationStack {
            if pc.isConfigured {
                pages
            } else {
                FirstRunView(pc: pc)
            }
        }
    }

    private var pages: some View {
        TabView(selection: $page) {
            VoicePage(pc: pc, orbState: $orbState)
                .tag(0)
                .navigationTitle("קול")

            PowerPage(pc: pc)
                .tag(1)
                .navigationTitle("חשמל")

            StatsPage(pc: pc)
                .tag(2)
                .navigationTitle("מצב")

            ActionsPage(pc: pc)
                .tag(3)
                .navigationTitle("כפתורים")
        }
        // Horizontal pages, deliberately: .verticalPage would claim the Digital
        // Crown, and the crown belongs to the volume on the first page.
        .tabViewStyle(.page)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Circle()
                    .fill(pc.isConnected ? Color.green : Color.orange)
                    .frame(width: 6, height: 6)
            }
            ToolbarItem(placement: .topBarTrailing) {
                NavigationLink {
                    SettingsView(pc: pc)
                } label: {
                    Image(systemName: "gearshape").font(.system(size: 11))
                }
            }
        }
        .task {
            await pc.loadDefinitions()
            await poll()
        }
    }

    /// One loop rather than several timers, so the watch wakes as rarely as
    /// the slowest thing allows.
    private func poll() async {
        var tick = 0
        while !Task.isCancelled {
            await pc.refreshStatus()
            if page == 2 { await pc.refreshStats() }
            if page == 3 || tick % 2 == 0 { await pc.refreshShortcutStatus() }
            tick += 1
            try? await Task.sleep(for: .seconds(3))
        }
    }
}

struct FirstRunView: View {
    @Bindable var pc: PCClient

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                Image(systemName: "desktopcomputer")
                    .font(.system(size: 34))
                    .foregroundStyle(.cyan)

                Text("חבר את המחשב")
                    .font(.headline)

                Text("הפעל את השרת במחשב ופתח את הדשבורד. הכתובת מופיעה בפינה שלו.")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)

                NavigationLink {
                    SettingsView(pc: pc)
                } label: {
                    Text("הזן כתובת")
                }
            }
            .padding()
        }
    }
}

struct SettingsView: View {
    @Bindable var pc: PCClient

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Text("כתובת המחשב ברשת")
                    .font(.system(size: 12, weight: .semibold))

                TextFieldLink(prompt: Text("למשל 192.168.1.20")) {
                    HStack {
                        Text(pc.host.isEmpty ? "לא הוגדר" : pc.host)
                            .font(.system(.body, design: .monospaced))
                            .foregroundStyle(pc.host.isEmpty ? .secondary : .primary)
                        Spacer()
                        Image(systemName: "pencil").font(.system(size: 12))
                    }
                } onSubmit: { entered in
                    pc.host = entered.trimmingCharacters(in: .whitespacesAndNewlines)
                    Task { await pc.refreshStatus(); await pc.loadDefinitions() }
                }

                Divider()

                HStack(spacing: 6) {
                    Circle()
                        .fill(pc.isConnected ? Color.green : Color.orange)
                        .frame(width: 6, height: 6)
                    Text(pc.isConnected ? "מחובר" : "אין קשר")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                }

                Text("השעון והמחשב חייבים להיות על אותה רשת Wi-Fi.")
                    .font(.system(size: 10))
                    .foregroundStyle(.tertiary)
            }
            .padding()
        }
        .navigationTitle("הגדרות")
    }
}
