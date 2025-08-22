#!/usr/bin/env swift

/*
TinyIntent Router Runner - M7.0: Router Refactor & Async Generation

Simple CLI interface to SmallIntent.mlmodel for routing decisions.
Returns JSON with route, intent, and confidence.
*/

import Foundation
import CoreML

struct RouterResult: Codable {
    let route: String
    let intent: String
    let confidence: Double
}

class IntentRouter {
    private let modelPath: String
    private let model: MLModel?
    
    init() {
        // Determine project root and model path
        let currentDir = FileManager.default.currentDirectoryPath
        let projectRoot = URL(fileURLWithPath: currentDir)
        
        self.modelPath = projectRoot
            .appendingPathComponent("router")
            .appendingPathComponent("SmallIntent.mlmodel")
            .path
        
        // Try to load the model
        if FileManager.default.fileExists(atPath: modelPath) {
            do {
                self.model = try MLModel(contentsOf: URL(fileURLWithPath: modelPath))
            } catch {
                print("Warning: Failed to load model: \(error)", to: &standardError)
                self.model = nil
            }
        } else {
            self.model = nil
        }
    }
    
    func route(text: String) -> RouterResult {
        guard let model = self.model else {
            return fallbackRouting(text: text)
        }
        
        do {
            // Create input features
            let inputFeatures = try MLDictionaryFeatureProvider(dictionary: ["text": text])
            
            // Make prediction
            let prediction = try model.prediction(from: inputFeatures)
            
            // Extract results
            var route = "gen"
            var confidence = 0.6
            var intent = "general_query"
            
            // Try to get the route/label prediction
            if let routeFeature = prediction.featureValue(for: "label") {
                route = routeFeature.stringValue ?? "gen"
            } else if let routeFeature = prediction.featureValue(for: "classLabel") {
                route = routeFeature.stringValue ?? "gen"
            }
            
            // Try to get confidence scores
            if let confidenceDict = prediction.featureValue(for: "classProbability")?.dictionaryValue {
                if let routeConfidence = confidenceDict[route] as? Double {
                    confidence = routeConfidence
                }
            }
            
            // Determine intent based on route and text content
            intent = determineIntent(route: route, text: text)
            
            return RouterResult(
                route: route,
                intent: intent,
                confidence: confidence
            )
            
        } catch {
            print("Prediction error: \(error)", to: &standardError)
            return fallbackRouting(text: text)
        }
    }
    
    private func determineIntent(route: String, text: String) -> String {
        let textLower = text.lowercased()
        
        if route == "act" {
            if textLower.contains("bot") || textLower.contains("position") || textLower.contains("trade") {
                return "bot_management"
            } else if textLower.contains("log") || textLower.contains("error") {
                return "system_monitoring"
            } else if textLower.contains("ssh") || textLower.contains("server") {
                return "infrastructure"
            } else {
                return "general_action"
            }
        } else {
            // Generation route
            if textLower.contains("explain") || textLower.contains("what") || textLower.contains("how") {
                return "explanation"
            } else if textLower.contains("help") || textLower.contains("assist") {
                return "assistance"
            } else {
                return "general_query"
            }
        }
    }
    
    private func fallbackRouting(text: String) -> RouterResult {
        let textLower = text.lowercased()
        
        // Check for action-oriented keywords
        if textLower.contains("bot") || textLower.contains("position") || 
           textLower.contains("trade") || textLower.contains("close") || 
           textLower.contains("stop") || textLower.contains("emergency") ||
           textLower.contains("execute") || textLower.contains("run") || 
           textLower.contains("do") {
            return RouterResult(
                route: "act",
                intent: "bot_management", 
                confidence: 0.7
            )
        }
        
        // Default to generation
        return RouterResult(
            route: "gen",
            intent: "general_query",
            confidence: 0.6
        )
    }
}

// Utility for stderr output
var standardError = FileHandle.standardError

extension FileHandle: TextOutputStream {
    public func write(_ string: String) {
        guard let data = string.data(using: .utf8) else { return }
        self.write(data)
    }
}

// Main execution
func main() {
    // Get command line arguments
    let args = CommandLine.arguments
    
    guard args.count >= 2 else {
        print("Usage: run_router.swift <text>", to: &standardError)
        exit(1)
    }
    
    let text = args[1]
    
    // Create router and get result
    let router = IntentRouter()
    let result = router.route(text: text)
    
    // Output JSON result
    do {
        let encoder = JSONEncoder()
        let jsonData = try encoder.encode(result)
        
        if let jsonString = String(data: jsonData, encoding: .utf8) {
            print(jsonString)
        } else {
            print("{\"route\":\"gen\",\"intent\":\"general_query\",\"confidence\":0.6}")
        }
    } catch {
        print("JSON encoding error: \(error)", to: &standardError)
        print("{\"route\":\"gen\",\"intent\":\"general_query\",\"confidence\":0.6}")
    }
}

main()