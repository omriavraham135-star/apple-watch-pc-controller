import Foundation
import WatchKit

class NetworkClient: ObservableObject {
    @Published var isConnected = false
    @Published var lastFeedback = "מוכן לפקודה"
    @Published var currentVolume: Int?
    @Published var isMuted: Bool = false

    func sendCommand(text: String, host: String, completion: @escaping (Bool, String) -> Void) {
        let cleanHost = host.trimmingCharacters(in: .whitespacesAndNewlines)
        let urlString = "http://\(cleanHost):8000/api/command"
        
        guard let url = URL(string: urlString) else {
            completion(false, "כתובת שגויה")
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 4.0

        let payload = ["text": text]
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        } catch {
            completion(false, "שגיאה בקידוד")
            return
        }

        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                if let error = error {
                    WKInterfaceDevice.current().play(.failure)
                    completion(false, "אין תקשורת ל-PC")
                    return
                }

                guard let data = data,
                      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                    WKInterfaceDevice.current().play(.failure)
                    completion(false, "תשובה לא תקינה")
                    return
                }

                let feedback = json["feedback"] as? String ?? "בוצע"
                if let details = json["details"] as? [String: Any] {
                    if let newVol = details["new_volume"] as? Int {
                        self.currentVolume = newVol
                    }
                    if let muted = details["is_muted"] as? Bool {
                        self.isMuted = muted
                    }
                }

                // Play pleasant success haptic tap
                WKInterfaceDevice.current().play(.success)
                self.lastFeedback = feedback
                completion(true, feedback)
            }
        }.resume()
    }

    func checkStatus(host: String) {
        let cleanHost = host.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: "http://\(cleanHost):8000/api/status") else { return }

        var request = URLRequest(url: url)
        request.timeoutInterval = 2.5

        URLSession.shared.dataTask(with: request) { data, _, error in
            DispatchQueue.main.async {
                if error == nil, let data = data,
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    self.isConnected = true
                    if let vol = json["volume"] as? Int {
                        self.currentVolume = vol
                    }
                    if let muted = json["is_muted"] as? Bool {
                        self.isMuted = muted
                    }
                } else {
                    self.isConnected = false
                }
            }
        }.resume()
    }
}
