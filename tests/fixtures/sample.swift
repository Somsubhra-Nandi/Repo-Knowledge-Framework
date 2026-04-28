import Foundation
import UIKit

protocol Processable {
    func process(input: String) -> String
}

class UserService: Processable {
    var name: String

    init(name: String) {
        self.name = name
    }

    func process(input: String) -> String {
        return formatOutput(input)
    }

    private func formatOutput(_ value: String) -> String {
        return "\(name): \(value)"
    }
}

struct Config {
    var debug: Bool
}

func topLevelHelper(text: String) -> String {
    return text.trimmingCharacters(in: .whitespaces)
}
