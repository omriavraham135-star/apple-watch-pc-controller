import SwiftUI

@main
struct iOSCompanionApp: App {
    var body: some Scene {
        WindowGroup {
            VStack(spacing: 16) {
                Image(systemName: "applewatch")
                    .font(.system(size: 60))
                    .foregroundColor(.cyan)
                
                Text("PC Volume Controller")
                    .font(.title2)
                    .fontWeight(.bold)
                
                Text("האפליקציה פועלת ישירות מתוך השעון שלך (Apple Watch). פתח את אפליקציית ה-Watch בשעון.")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }
            .padding()
        }
    }
}
