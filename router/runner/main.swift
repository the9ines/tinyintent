#!/usr/bin/env swift

import Foundation
import CoreML

/// TinyIntent Router CLI Runner
/// Simple command-line interface for the SmallIntent.mlmodel
/// Usage: swift main.swift "text to classify"
/// Returns: gen or act (exit code 0 for success)

func main() {
    // Get command line arguments
    let arguments = CommandLine.arguments
    guard arguments.count >= 2 else {
        fputs("Usage: swift main.swift \"text to classify\"\n", stderr)
        exit(1)
    }
    
    let inputText = arguments[1]
    let projectRoot = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    let modelPath = projectRoot.appendingPathComponent("SmallIntent.mlmodel")
    
    // Check if model exists
    guard FileManager.default.fileExists(atPath: modelPath.path) else {
        fputs("Error: SmallIntent.mlmodel not found. Run 'make router-train' first.\n", stderr)
        exit(1)
    }
    
    do {
        // Load model
        let model = try MLModel(contentsOf: modelPath)
        
        // Make prediction
        let inputFeatures = try MLDictionaryFeatureProvider(dictionary: ["text": inputText])
        let prediction = try model.prediction(from: inputFeatures)
        
        // Extract result
        guard let predictedLabel = prediction.featureValue(for: "classLabel")?.stringValue else {
            fputs("Error: Could not extract prediction from model\n", stderr)
            exit(1)
        }
        
        // Output result
        print(predictedLabel)
        exit(0)
        
    } catch {
        fputs("Error: \(error)\n", stderr)
        exit(1)
    }
}

// Entry point
main()