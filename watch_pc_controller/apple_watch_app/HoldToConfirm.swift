import SwiftUI
import WatchKit

/// The outline of a rounded rectangle, starting at top centre and running
/// clockwise.
///
/// `RoundedRectangle` would work with `.trim`, but its path begins at a corner,
/// so the progress would start from an arbitrary-looking place. Tracing it by
/// hand puts the start where a clock would put it.
struct TileOutline: Shape {
    var cornerRadius: CGFloat

    func path(in rect: CGRect) -> Path {
        var path = Path()
        let r = min(cornerRadius, rect.width / 2, rect.height / 2)

        path.move(to: CGPoint(x: rect.midX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX - r, y: rect.minY))
        path.addArc(
            center: CGPoint(x: rect.maxX - r, y: rect.minY + r), radius: r,
            startAngle: .degrees(-90), endAngle: .degrees(0), clockwise: false)
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY - r))
        path.addArc(
            center: CGPoint(x: rect.maxX - r, y: rect.maxY - r), radius: r,
            startAngle: .degrees(0), endAngle: .degrees(90), clockwise: false)
        path.addLine(to: CGPoint(x: rect.minX + r, y: rect.maxY))
        path.addArc(
            center: CGPoint(x: rect.minX + r, y: rect.maxY - r), radius: r,
            startAngle: .degrees(90), endAngle: .degrees(180), clockwise: false)
        path.addLine(to: CGPoint(x: rect.minX, y: rect.minY + r))
        path.addArc(
            center: CGPoint(x: rect.minX + r, y: rect.minY + r), radius: r,
            startAngle: .degrees(180), endAngle: .degrees(270), clockwise: false)
        path.closeSubpath()
        return path
    }
}

/// A tile that only fires after a deliberate press and hold.
///
/// This is a touchscreen strapped to a wrist. A stray brush against shutdown
/// must not cost someone their unsaved work, so the commitment is made
/// visible: a ring closes around the tile, the accent floods up from the base,
/// a countdown reads out the seconds, and the haptic pulse quickens as the
/// moment approaches. Letting go unwinds all of it — the cancel is as legible
/// as the commit.
struct HoldToConfirm<Content: View>: View {

    let seconds: Double
    let accent: Color
    let onCommit: () -> Void
    @ViewBuilder var content: (Bool) -> Content

    @State private var progress: Double = 0
    @State private var isHolding = false
    @State private var justCommitted = false
    @State private var driver: Task<Void, Never>?

    private let corner: CGFloat = 18

    var body: some View {
        ZStack {
            TileChrome(accent: accent, lit: justCommitted)

            // the accent rising from the base
            GeometryReader { geo in
                accent
                    .opacity(0.85)
                    .frame(height: geo.size.height * progress)
                    .frame(maxHeight: .infinity, alignment: .bottom)
            }
            .clipShape(RoundedRectangle(cornerRadius: corner, style: .continuous))

            TileOutline(cornerRadius: corner)
                .stroke(Color.white.opacity(0.13), lineWidth: 2)
                .padding(1.5)

            TileOutline(cornerRadius: corner)
                .trim(from: 0, to: progress)
                .stroke(Color.white, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                .padding(1.5)
                .opacity(isHolding || justCommitted ? 1 : 0)
                .shadow(color: .white.opacity(0.7), radius: 4)

            content(isHolding)
                .opacity(isHolding ? 0 : 1)

            if isHolding {
                Text("\(Int(ceil(seconds * (1 - progress))))")
                    .font(.system(size: 26, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.white)
                    .shadow(color: .black.opacity(0.5), radius: 4)
            }
        }
        .aspectRatio(1, contentMode: .fit)
        .contentShape(RoundedRectangle(cornerRadius: corner, style: .continuous))
        .scaleEffect(isHolding ? 0.97 : 1)
        .animation(.spring(response: 0.3, dampingFraction: 0.8), value: isHolding)
        // A drag with no minimum distance is the only reliable way to learn
        // when a finger lands and when it leaves; a long-press gesture reports
        // neither the moment of contact nor the progress in between.
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in if !isHolding { begin() } }
                .onEnded { _ in cancel() }
        )
        .onDisappear { driver?.cancel() }
    }

    private func begin() {
        isHolding = true
        progress = 0
        WKInterfaceDevice.current().play(.start)

        driver?.cancel()
        driver = Task { @MainActor in
            let startedAt = Date()
            var lastBuzz = Date.distantPast

            while !Task.isCancelled {
                let elapsed = Date().timeIntervalSince(startedAt)
                let value = min(1, elapsed / seconds)
                progress = value

                // The pulse tightens from roughly three a second to twelve, so
                // the wrist knows the commit is coming without looking.
                let interval = 0.32 - value * 0.24
                if Date().timeIntervalSince(lastBuzz) > interval {
                    WKInterfaceDevice.current().play(.click)
                    lastBuzz = Date()
                }

                if value >= 1 {
                    commit()
                    return
                }
                try? await Task.sleep(for: .milliseconds(16))
            }
        }
    }

    private func commit() {
        isHolding = false
        justCommitted = true
        progress = 1
        WKInterfaceDevice.current().play(.success)
        onCommit()

        // The ring stays closed through the confirmation, then rewinds while
        // hidden, so the next press never begins on a full ring.
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(700))
            justCommitted = false
            withAnimation(.easeOut(duration: 0.25)) { progress = 0 }
        }
    }

    private func cancel() {
        driver?.cancel()
        driver = nil
        guard isHolding else { return }
        isHolding = false
        WKInterfaceDevice.current().play(.retry)
        withAnimation(.easeOut(duration: 0.28)) { progress = 0 }
    }
}

/// The shared look of every tile: a tinted well with a lit top edge.
struct TileChrome: View {
    let accent: Color
    var lit: Bool = false

    var body: some View {
        RoundedRectangle(cornerRadius: 18, style: .continuous)
            .fill(
                LinearGradient(
                    colors: [accent.opacity(lit ? 0.5 : 0.24), Color.white.opacity(0.04)],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .strokeBorder(accent.opacity(lit ? 0.95 : 0.3), lineWidth: 1)
            )
            .overlay(alignment: .top) {
                // the hairline that catches light, the way Control Center tiles do
                LinearGradient(
                    colors: [.clear, .white.opacity(0.35), .clear],
                    startPoint: .leading, endPoint: .trailing
                )
                .frame(height: 1)
                .padding(.horizontal, 10)
            }
            .shadow(color: accent.opacity(lit ? 0.8 : 0), radius: lit ? 12 : 0)
            .animation(.easeOut(duration: 0.35), value: lit)
    }
}

/// The icon puck that sits at the centre of a tile.
struct TileGlyph: View {
    let systemName: String
    let accent: Color
    var filled: Bool = false

    var body: some View {
        Image(systemName: systemName)
            .font(.system(size: 17, weight: .medium))
            .foregroundStyle(filled ? Color.white : accent)
            .frame(width: 36, height: 36)
            .background {
                Circle()
                    .fill(
                        LinearGradient(
                            colors: filled
                                ? [accent, accent.opacity(0.7)]
                                : [accent.opacity(0.25), accent.opacity(0.07)],
                            startPoint: .topLeading, endPoint: .bottomTrailing
                        )
                    )
                    .overlay(Circle().strokeBorder(.white.opacity(filled ? 0.3 : 0.15), lineWidth: 1))
            }
            .shadow(color: filled ? accent.opacity(0.8) : .clear, radius: 8)
            .animation(.easeOut(duration: 0.3), value: filled)
    }
}
