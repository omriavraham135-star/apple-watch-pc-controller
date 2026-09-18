import SwiftUI

enum AssistantState {
    case idle
    case listening
    case thinking
    case executing
    case success
    case error
}

struct VoiceOrbVisualizer: View {
    let state: AssistantState
    let audioLevel: CGFloat // 0.0 to 1.0

    @State private var rotation: Double = 0
    @State private var pulse: CGFloat = 1.0

    var body: some View {
        ZStack {
            // Background ambient glow aura
            Circle()
                .fill(auraGradient)
                .frame(width: 140, height: 140)
                .blur(radius: 24)
                .opacity(auraOpacity)
                .scaleEffect(pulse)

            // The main animated fluid sphere
            ZStack {
                Circle()
                    .fill(sphereGradient)
                    .frame(width: 100, height: 100)
                    .rotationEffect(.degrees(rotation))
                    .overlay(
                        Circle()
                            .stroke(Color.white.opacity(0.35), lineWidth: 1.5)
                    )
                    .shadow(color: shadowColor, radius: 16)

                // Fluid inner lighting / reflections
                Circle()
                    .fill(
                        RadialGradient(
                            gradient: Gradient(colors: [Color.white.opacity(0.7), Color.clear]),
                            center: .topLeading,
                            startRadius: 5,
                            endRadius: 55
                        )
                    )
                    .frame(width: 98, height: 98)

                // Waveform bars visible during listening/executing
                if state == .listening || state == .executing {
                    HStack(spacing: 3) {
                        ForEach(0..<5) { index in
                            WaveBar(audioLevel: audioLevel, index: index)
                        }
                    }
                }
            }
            .scaleEffect(sphereScale)
        }
        .onAppear {
            startAnimation()
        }
        .onChange(of: state) { _ in
            startAnimation()
        }
    }

    private func startAnimation() {
        switch state {
        case .idle:
            withAnimation(.easeInOut(duration: 3.5).repeatForever(autoreverses: true)) {
                pulse = 1.05
                rotation = 360
            }
        case .listening:
            withAnimation(.easeInOut(duration: 1.0).repeatForever(autoreverses: true)) {
                pulse = 1.15
            }
        case .thinking:
            withAnimation(.linear(duration: 2.0).repeatForever(autoreverses: false)) {
                rotation += 360
                pulse = 1.08
            }
        case .executing:
            withAnimation(.easeInOut(duration: 0.7).repeatForever(autoreverses: true)) {
                pulse = 1.2
            }
        case .success:
            withAnimation(.spring(response: 0.4, dampingFraction: 0.6)) {
                pulse = 1.25
            }
        case .error:
            withAnimation(.default) {
                pulse = 0.95
            }
        }
    }

    private var sphereScale: CGFloat {
        switch state {
        case .listening:
            return 1.0 + (audioLevel * 0.15)
        case .executing:
            return 1.08
        case .success:
            return 1.05
        default:
            return 1.0
        }
    }

    private var auraOpacity: Double {
        switch state {
        case .idle: return 0.35
        case .listening: return 0.75
        case .thinking: return 0.85
        case .executing: return 0.9
        case .success: return 0.8
        case .error: return 0.5
        }
    }

    private var auraGradient: RadialGradient {
        switch state {
        case .idle:
            return RadialGradient(
                colors: [Color.blue.opacity(0.6), Color.purple.opacity(0.3), Color.clear],
                center: .center, startRadius: 10, endRadius: 70
            )
        case .listening:
            return RadialGradient(
                colors: [Color.cyan, Color.purple.opacity(0.6), Color.clear],
                center: .center, startRadius: 10, endRadius: 70
            )
        case .thinking:
            return RadialGradient(
                colors: [Color.purple, Color.pink.opacity(0.7), Color.clear],
                center: .center, startRadius: 10, endRadius: 70
            )
        case .executing:
            return RadialGradient(
                colors: [Color.blue, Color.green.opacity(0.7), Color.clear],
                center: .center, startRadius: 10, endRadius: 70
            )
        case .success:
            return RadialGradient(
                colors: [Color.green, Color.mint.opacity(0.6), Color.clear],
                center: .center, startRadius: 10, endRadius: 70
            )
        case .error:
            return RadialGradient(
                colors: [Color.red, Color.orange.opacity(0.5), Color.clear],
                center: .center, startRadius: 10, endRadius: 70
            )
        }
    }

    private var sphereGradient: AngularGradient {
        switch state {
        case .idle:
            return AngularGradient(
                gradient: Gradient(colors: [Color.cyan.opacity(0.8), Color.purple, Color.blue, Color.cyan.opacity(0.8)]),
                center: .center
            )
        case .listening:
            return AngularGradient(
                gradient: Gradient(colors: [Color.cyan, Color.blue, Color.purple, Color.pink, Color.cyan]),
                center: .center
            )
        case .thinking:
            return AngularGradient(
                gradient: Gradient(colors: [Color.purple, Color.pink, Color.indigo, Color.purple]),
                center: .center
            )
        case .executing:
            return AngularGradient(
                gradient: Gradient(colors: [Color.blue, Color.teal, Color.green, Color.blue]),
                center: .center
            )
        case .success:
            return AngularGradient(
                gradient: Gradient(colors: [Color.green, Color.mint, Color.teal, Color.green]),
                center: .center
            )
        case .error:
            return AngularGradient(
                gradient: Gradient(colors: [Color.red, Color.orange, Color.red]),
                center: .center
            )
        }
    }

    private var shadowColor: Color {
        switch state {
        case .idle: return Color.blue.opacity(0.4)
        case .listening: return Color.cyan.opacity(0.7)
        case .thinking: return Color.purple.opacity(0.8)
        case .executing: return Color.teal.opacity(0.8)
        case .success: return Color.green.opacity(0.9)
        case .error: return Color.red.opacity(0.6)
        }
    }
}

struct WaveBar: View {
    let audioLevel: CGFloat
    let index: Int
    @State private var height: CGFloat = 8

    var body: some View {
        RoundedRectangle(cornerRadius: 2)
            .fill(Color.white.opacity(0.9))
            .frame(width: 3, height: max(6, height))
            .onAppear {
                withAnimation(
                    .easeInOut(duration: 0.3 + Double(index) * 0.1)
                    .repeatForever(autoreverses: true)
                ) {
                    height = CGFloat([18, 28, 36, 24, 14][index]) * (0.5 + audioLevel * 0.5)
                }
            }
    }
}
