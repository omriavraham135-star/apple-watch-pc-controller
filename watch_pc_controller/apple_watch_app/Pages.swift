import SwiftUI
import WatchKit

// MARK: - Shared palette

enum Accent {
    static let power: [String: Color] = [
        "lock": Color(red: 0.25, green: 0.78, blue: 0.88),
        "sleep": Color(red: 0.37, green: 0.36, blue: 0.90),
        "restart": Color(red: 1.00, green: 0.62, blue: 0.04),
        "shutdown": Color(red: 1.00, green: 0.27, blue: 0.23),
    ]

    static let shortcuts: [String: Color] = [
        "screenshot": Color(red: 0.25, green: 0.78, blue: 0.88),
        "minimize-all": Color(red: 0.37, green: 0.36, blue: 0.90),
        "chrome": Color(red: 1.00, green: 0.62, blue: 0.04),
        "explorer": Color(red: 1.00, green: 0.84, blue: 0.04),
        "taskmgr": Color(red: 0.75, green: 0.35, blue: 0.95),
        "settings": Color(red: 0.60, green: 0.60, blue: 0.62),
    ]

    private static let pool: [Color] = [
        Color(red: 0.04, green: 0.52, blue: 1.00),
        Color(red: 0.19, green: 0.82, blue: 0.35),
        Color(red: 1.00, green: 0.22, blue: 0.37),
        Color(red: 0.39, green: 0.82, blue: 1.00),
        Color(red: 0.75, green: 0.35, blue: 0.95),
        Color(red: 1.00, green: 0.62, blue: 0.04),
    ]

    /// A stable colour for an id the palette does not name, so a shortcut added
    /// to actions.json never lands in a grey grid.
    static func forShortcut(_ id: String) -> Color {
        if let known = shortcuts[id] { return known }
        var hash = 0
        for byte in id.unicodeScalars { hash = (hash &* 31 &+ Int(byte.value)) & 0xFFFFFF }
        return pool[hash % pool.count]
    }

    static func forPower(_ action: String) -> Color {
        power[action] ?? Color(red: 0.25, green: 0.78, blue: 0.88)
    }
}

enum Glyph {
    static let power: [String: String] = [
        "lock": "lock.fill",
        "sleep": "moon.fill",
        "restart": "arrow.clockwise",
        "shutdown": "power",
    ]

    /// actions.json names SF Symbols directly. An unknown symbol renders as
    /// nothing, so an empty name falls back rather than leaving a hole.
    static func shortcut(_ name: String) -> String {
        name.isEmpty ? "bolt.fill" : name
    }
}

// MARK: - Voice

struct VoicePage: View {
    @Bindable var pc: PCClient
    @Binding var orbState: OrbState

    @State private var volumeValue: Double = 50

    var body: some View {
        VStack(spacing: 6) {
            Spacer(minLength: 0)

            TextFieldLink(prompt: Text("אמור פקודה")) {
                OrbView(configuration: orbState.configuration)
                    .frame(width: 104, height: 104)
            } onSubmit: { spoken in
                handle(spoken)
            }
            .buttonStyle(.plain)

            if !pc.lastMessage.isEmpty {
                Text(pc.lastMessage)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }

            Spacer(minLength: 0)

            // The slider only moves the binding. Posting happens in one place
            // below, so a drag cannot send the same value twice.
            VolumeSlider(value: $volumeValue)
        }
        .focusable()
        .digitalCrownRotation(
            $volumeValue, from: 0, through: 100, by: 2,
            sensitivity: .medium, isContinuous: false, isHapticFeedbackEnabled: true
        )
        .onChange(of: volumeValue) { _, newValue in
            // Adopting the value the server just reported would otherwise post
            // it straight back, and the two would chase each other. Equality is
            // the guard: a value that already matches the server is not news.
            let target = Int(newValue)
            guard target != pc.volume else { return }
            Task { await pc.setVolume(target) }
        }
        .onChange(of: pc.volume) { _, newValue in
            volumeValue = Double(newValue)
        }
        .onAppear { volumeValue = Double(pc.volume) }
    }

    private func handle(_ spoken: String) {
        let text = spoken.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        orbState = .thinking
        Task {
            switch await pc.send(command: text) {
            case .understood:
                orbState = .success
                WKInterfaceDevice.current().play(.success)
            case .notUnderstood, .failed:
                orbState = .error
                WKInterfaceDevice.current().play(.failure)
            }
            try? await Task.sleep(for: .milliseconds(1900))
            orbState = .idle
        }
    }
}

/// The capsule slider, sized for a thumb rather than a cursor.
struct VolumeSlider: View {
    @Binding var value: Double

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(.white.opacity(0.1))
                    .overlay(Capsule().strokeBorder(.white.opacity(0.14), lineWidth: 1))

                Capsule()
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(red: 0.04, green: 0.52, blue: 1.0),
                                Color(red: 0.25, green: 0.78, blue: 0.88),
                                Color(red: 0.37, green: 0.36, blue: 0.90),
                            ],
                            startPoint: .leading, endPoint: .trailing
                        )
                    )
                    .frame(width: max(16, geo.size.width * value / 100))

                HStack {
                    Image(systemName: "speaker.fill").font(.system(size: 9))
                    Spacer()
                    Text("\(Int(value))%")
                        .font(.system(size: 12, weight: .bold, design: .rounded))
                        .monospacedDigit()
                    Spacer()
                    Image(systemName: "speaker.wave.3.fill").font(.system(size: 9))
                }
                .foregroundStyle(.white)
                .padding(.horizontal, 10)
            }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { drag in
                        let ratio = min(max(0, drag.location.x / geo.size.width), 1)
                        value = (ratio * 100).rounded()
                    }
            )
        }
        .frame(height: 32)
    }
}

// MARK: - Power

struct PowerPage: View {
    @Bindable var pc: PCClient

    private let columns = [GridItem(.flexible(), spacing: 6), GridItem(.flexible(), spacing: 6)]

    var body: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 6) {
                ForEach(pc.powerActions) { action in
                    let accent = Accent.forPower(action.action)
                    let glyph = Glyph.power[action.action] ?? "bolt.fill"

                    if action.holdSeconds > 0 {
                        HoldToConfirm(
                            seconds: action.holdSeconds,
                            accent: accent,
                            onCommit: { Task { _ = await pc.run(power: action.action) } }
                        ) { _ in
                            PowerTileFace(label: action.label, glyph: glyph, accent: accent)
                        }
                    } else {
                        Button {
                            WKInterfaceDevice.current().play(.click)
                            Task { _ = await pc.run(power: action.action) }
                        } label: {
                            ZStack {
                                TileChrome(accent: accent)
                                PowerTileFace(label: action.label, glyph: glyph, accent: accent)
                            }
                            .aspectRatio(TileMetrics.aspect, contentMode: .fit)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(.horizontal, 2)
            .padding(.bottom, TileMetrics.pageBottomInset)
        }
    }
}

struct PowerTileFace: View {
    let label: String
    let glyph: String
    let accent: Color

    var body: some View {
        VStack(spacing: 6) {
            TileGlyph(systemName: glyph, accent: accent)
            Text(label)
                .font(.system(size: 11, weight: .semibold))
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
        .padding(4)
    }
}

// MARK: - Machine vitals

struct StatsPage: View {
    @Bindable var pc: PCClient

    var body: some View {
        VStack(spacing: 10) {
            ZStack {
                ring(fraction: fraction(\.cpu), radius: 46, colour: Color(red: 0.04, green: 0.52, blue: 1.0))
                ring(fraction: fraction(\.memory), radius: 34, colour: Color(red: 0.75, green: 0.35, blue: 0.95))
                ring(fraction: fraction(\.disk), radius: 22, colour: Color(red: 0.19, green: 0.82, blue: 0.35))
            }
            .frame(width: 104, height: 104)

            VStack(spacing: 3) {
                legend("מעבד", pc.stats?.cpu, Color(red: 0.04, green: 0.52, blue: 1.0), note: nil)
                legend("זיכרון", pc.stats?.memory, Color(red: 0.75, green: 0.35, blue: 0.95),
                       note: pc.stats.map { "\($0.memoryUsedGB)/\($0.memoryTotalGB)GB" })
                legend("דיסק", pc.stats?.disk, Color(red: 0.19, green: 0.82, blue: 0.35),
                       note: pc.stats.map { "\($0.diskFreeGB)GB פנוי" })
            }
        }
        .padding(.horizontal, 4)
    }

    private func fraction(_ key: KeyPath<MachineStats, Int>) -> Double {
        guard let stats = pc.stats else { return 0 }
        return Double(stats[keyPath: key]) / 100
    }

    private func ring(fraction: Double, radius: CGFloat, colour: Color) -> some View {
        ZStack {
            Circle().stroke(.white.opacity(0.1), lineWidth: 9)
            Circle()
                .trim(from: 0, to: fraction)
                .stroke(colour, style: StrokeStyle(lineWidth: 9, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(.easeOut(duration: 0.5), value: fraction)
        }
        .frame(width: radius * 2, height: radius * 2)
    }

    private func legend(_ name: String, _ value: Int?, _ colour: Color, note: String?) -> some View {
        HStack(spacing: 6) {
            Circle().fill(colour).frame(width: 6, height: 6)
            Text(name).font(.system(size: 11)).foregroundStyle(.secondary)
            if let note {
                Text(note).font(.system(size: 9)).foregroundStyle(.tertiary).lineLimit(1)
            }
            Spacer()
            Text(value.map { "\($0)%" } ?? "–")
                .font(.system(size: 11, weight: .bold))
                .monospacedDigit()
        }
    }
}

// MARK: - Shortcuts

struct ActionsPage: View {
    @Bindable var pc: PCClient

    @State private var confirmed: Set<String> = []
    @State private var raised: Set<String> = []

    private let columns = [GridItem(.flexible(), spacing: 6), GridItem(.flexible(), spacing: 6)]

    var body: some View {
        ScrollView {
            if pc.shortcuts.isEmpty {
                Text("אין כפתורים.\nערוך את actions.json במחשב.")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.top, 30)
            } else {
                LazyVGrid(columns: columns, spacing: 6) {
                    ForEach(pc.shortcuts) { shortcut in
                        tile(for: shortcut)
                    }
                }
                .padding(.horizontal, 2)
                .padding(.bottom, TileMetrics.pageBottomInset)
            }
        }
    }

    private func tile(for shortcut: Shortcut) -> some View {
        let accent = Accent.forShortcut(shortcut.id)
        let isRunning = pc.shortcutStatus[shortcut.id] ?? false
        let isConfirmed = confirmed.contains(shortcut.id)

        return Button {
            fire(shortcut)
        } label: {
            ZStack {
                TileChrome(accent: accent, lit: isRunning || isConfirmed)

                VStack(spacing: 6) {
                    if isConfirmed {
                        Image(systemName: "checkmark")
                            .font(.system(size: 20, weight: .bold))
                            .foregroundStyle(.white)
                            .frame(width: 36, height: 36)
                    } else {
                        TileGlyph(systemName: Glyph.shortcut(shortcut.icon), accent: accent, filled: isRunning)
                    }
                    Text(shortcut.label)
                        .font(.system(size: 10.5, weight: .semibold))
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                        .foregroundStyle(isRunning ? .primary : .secondary)
                }
                .padding(4)

                // the quiet pip that says this app is already open
                if isRunning {
                    Circle()
                        .fill(accent)
                        .frame(width: 5, height: 5)
                        .shadow(color: accent, radius: 3)
                        .frame(maxWidth: .infinity, maxHeight: .infinity,
                               alignment: .topTrailing)
                        .padding(8)
                }
            }
            .aspectRatio(TileMetrics.aspect, contentMode: .fit)
            .offset(y: raised.contains(shortcut.id) ? -6 : 0)
            .animation(.spring(response: 0.35, dampingFraction: 0.55), value: raised)
        }
        .buttonStyle(.plain)
    }

    private func fire(_ shortcut: Shortcut) {
        WKInterfaceDevice.current().play(.click)
        Task {
            switch await pc.run(shortcut: shortcut.id) {
            case .launched:
                WKInterfaceDevice.current().play(.success)
                confirmed.insert(shortcut.id)
                try? await Task.sleep(for: .milliseconds(1100))
                confirmed.remove(shortcut.id)
            case .raised:
                // Raising a window that was already open is a different event
                // from starting the app, so it gets a lift rather than a tick.
                WKInterfaceDevice.current().play(.directionUp)
                raised.insert(shortcut.id)
                try? await Task.sleep(for: .milliseconds(700))
                raised.remove(shortcut.id)
            case .failed:
                WKInterfaceDevice.current().play(.failure)
            }
            await pc.refreshShortcutStatus()
        }
    }
}
