import SwiftUI
import WatchKit

struct ContentView: View {
    @AppStorage("pc_ip_address") private var pcIpAddress = ""
    @StateObject private var network = NetworkClient()
    
    @State private var state: AssistantState = .idle
    @State private var audioLevel: CGFloat = 0.5
    @State private var volumeValue: Double = 50.0

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Minimal Top Bar: Status dot + Time + Volume Badge
                HStack {
                    Circle()
                        .fill(network.isConnected ? Color.green : Color.orange)
                        .frame(width: 6, height: 6)

                    Spacer()

                    Text("\(Int(volumeValue))%")
                        .font(.system(size: 13, weight: .bold, design: .rounded))
                        .foregroundColor(.cyan)

                    NavigationLink(destination: SettingsView(ipAddress: $pcIpAddress)) {
                        Image(systemName: "gearshape")
                            .font(.system(size: 10))
                            .foregroundColor(.gray.opacity(0.6))
                    }
                    .buttonStyle(.plain)
                    .padding(.leading, 4)
                }
                .padding(.horizontal, 10)
                .padding(.top, 2)

                Spacer()

                // Center Stage: Pure Voice Orb (tap to talk)
                Button(action: startVoiceInput) {
                    VoiceOrbVisualizer(state: state, audioLevel: audioLevel)
                }
                .buttonStyle(.plain)

                Spacer()

                // Pure Apple Capsule Volume Slider
                AppleVolumeSlider(value: $volumeValue, onVolumeChanged: { newVol in
                    sendDirectVolume(newVol)
                })
                .padding(.horizontal, 4)
                .padding(.bottom, 4)
            }
            .focusable()
            .digitalCrownRotation(
                $volumeValue,
                from: 0.0,
                through: 100.0,
                by: 2.0,
                sensitivity: .medium,
                isContinuous: false,
                isHapticFeedbackEnabled: true
            )
            .onChange(of: volumeValue) { newVal in
                sendDirectVolume(Int(newVal))
            }
            .onAppear {
                network.checkStatus(host: pcIpAddress)
            }
            .onChange(of: network.currentVolume) { newVol in
                if let newVol = newVol {
                    volumeValue = Double(newVol)
                }
            }
        }
    }

    private func startVoiceInput() {
        WKInterfaceDevice.current().play(.click)
        state = .listening

        WKExtension.shared().visibleInterfaceController?.presentTextInputController(
            withSuggestions: ["תנמיך ב-50 אחוז", "תנמיך ל-50 אחוז", "תגביר ב-20 אחוז", "תשתיק"],
            allowedInputMode: .plain
        ) { results in
            guard let results = results, let spokenText = results.first as? String, !spokenText.isEmpty else {
                state = .idle
                return
            }

            state = .thinking

            network.sendCommand(text: spokenText, host: pcIpAddress) { success, _ in
                state = success ? .success : .error
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.8) {
                    state = .idle
                }
            }
        }
    }

    private func sendDirectVolume(_ vol: Int) {
        guard let url = URL(string: "http://\(pcIpAddress):8000/api/volume") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["volume": vol])
        req.timeoutInterval = 1.0
        URLSession.shared.dataTask(with: req).resume()
    }
}

// Minimalist Apple-Style Capsule Volume Slider
struct AppleVolumeSlider: View {
    @Binding var value: Double
    var onVolumeChanged: (Int) -> Void

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                // Frosted Glass Track
                Capsule()
                    .fill(Color.white.opacity(0.1))
                    .overlay(
                        Capsule()
                            .stroke(Color.white.opacity(0.15), lineWidth: 1)
                    )

                // Glowing Active Gradient Fill
                Capsule()
                    .fill(
                        LinearGradient(
                            colors: [Color.blue, Color.cyan, Color.indigo.opacity(0.8)],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .frame(width: max(16, geometry.size.width * CGFloat(value / 100.0)))
                    .shadow(color: Color.cyan.opacity(0.45), radius: 5)

                // Minimalist Icons & Value
                HStack {
                    Image(systemName: "speaker.fill")
                        .font(.system(size: 9))
                        .foregroundColor(.white.opacity(0.85))

                    Spacer()

                    Text("\(Int(value))%")
                        .font(.system(size: 11, weight: .bold, design: .rounded))
                        .foregroundColor(.white)

                    Spacer()

                    Image(systemName: "speaker.wave.3.fill")
                        .font(.system(size: 9))
                        .foregroundColor(.white.opacity(0.85))
                }
                .padding(.horizontal, 10)
            }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { gesture in
                        let pct = min(max(0, gesture.location.x / geometry.size.width), 1.0)
                        let newTarget = Double(round(pct * 100))
                        value = newTarget
                        onVolumeChanged(Int(newTarget))
                    }
            )
        }
        .frame(height: 32)
    }
}

struct SettingsView: View {
    @Binding var ipAddress: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("הגדרות שרת PC")
                .font(.headline)
            
            Text("כתובת IP ברשת ה-Wi-Fi:")
                .font(.caption)
                .foregroundColor(.gray)

            TextField("IP Address", text: $ipAddress)
                .font(.system(.body, design: .monospaced))

            Text("הכתובת מוצגת בדשבורד במחשב")
                .font(.footnote)
                .foregroundColor(.secondary)
        }
        .padding()
    }
}
