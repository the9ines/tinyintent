#!/usr/bin/env swift

import Foundation
import CoreML

/// TinyIntent Router Evaluation Script
/// Evaluates the trained SmallIntent.mlmodel against test data
/// Measures accuracy, latency, and provides detailed metrics

func main() {
    print("📊 TinyIntent Router Evaluation - M3")
    print("====================================")
    
    // Configuration
    let projectRoot = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    let modelPath = projectRoot.appendingPathComponent("router/SmallIntent.mlmodel")
    let testDataPath = projectRoot.appendingPathComponent("router/data/intents.tsv")
    
    print("🎯 Model: \(modelPath.path)")
    print("📁 Test data: \(testDataPath.path)")
    
    // Check if model exists
    guard FileManager.default.fileExists(atPath: modelPath.path) else {
        print("❌ ERROR: Model not found. Run 'make router-train' first.")
        exit(1)
    }
    
    do {
        // Load the model
        print("\n🔄 Loading model...")
        let model = try MLModel(contentsOf: modelPath)
        
        // Get model metadata
        let modelSize = try FileManager.default.attributesOfItem(atPath: modelPath.path)[.size] as! Int64
        let modelSizeMB = Double(modelSize) / (1024 * 1024)
        
        print("✓ Model loaded successfully")
        print("📏 Model size: \(String(format: "%.2f", modelSizeMB)) MB")
        print("📱 Model metadata:")
        print("   - Version: \(model.modelDescription.metadata[.versionString] ?? "Unknown")")
        print("   - Author: \(model.modelDescription.metadata[.author] ?? "TinyIntent")")
        print("   - Description: \(model.modelDescription.metadata[.description] ?? "Intent Router")")
        
        // Load test data
        print("\n📊 Loading test data...")
        let testData = try String(contentsOf: testDataPath, encoding: .utf8)
        let lines = testData.components(separatedBy: .newlines).dropFirst() // Skip header
        
        var testCases: [(text: String, label: String)] = []
        for line in lines {
            let components = line.components(separatedBy: "\t")
            if components.count >= 2 && !line.isEmpty {
                testCases.append((text: components[0], label: components[1]))
            }
        }
        
        print("✓ Loaded \(testCases.count) test cases")
        
        // Evaluate model performance
        print("\n🧪 Running evaluation...")
        var correctPredictions = 0
        var totalLatency: TimeInterval = 0
        var labelConfusion: [String: [String: Int]] = [:]
        var predictions: [(input: String, expected: String, predicted: String, confidence: Double, latency: TimeInterval)] = []
        
        for (index, testCase) in testCases.enumerated() {
            let startTime = CFAbsoluteTimeGetCurrent()
            
            // Make prediction
            let inputFeatures = try MLDictionaryFeatureProvider(dictionary: ["text": testCase.text])
            let prediction = try model.prediction(from: inputFeatures)
            
            let endTime = CFAbsoluteTimeGetCurrent()
            let latency = (endTime - startTime) * 1000 // Convert to milliseconds
            totalLatency += latency
            
            // Extract prediction results
            let predictedLabel = prediction.featureValue(for: "classLabel")?.stringValue ?? "unknown"
            let classProbabilities = prediction.featureValue(for: "classLabelProbs")?.dictionaryValue ?? [:]
            let confidence = classProbabilities[predictedLabel]?.doubleValue ?? 0.0
            
            predictions.append((
                input: testCase.text,
                expected: testCase.label,
                predicted: predictedLabel,
                confidence: confidence,
                latency: latency
            ))
            
            // Track accuracy
            if predictedLabel == testCase.label {
                correctPredictions += 1
            }
            
            // Build confusion matrix
            if labelConfusion[testCase.label] == nil {
                labelConfusion[testCase.label] = [:]
            }
            labelConfusion[testCase.label]![predictedLabel, default: 0] += 1
            
            // Progress indicator
            if (index + 1) % 10 == 0 || index == testCases.count - 1 {
                print("   Processed \(index + 1)/\(testCases.count) test cases...")
            }
        }
        
        // Calculate metrics
        let accuracy = Double(correctPredictions) / Double(testCases.count)
        let averageLatency = totalLatency / Double(testCases.count)
        
        print("\n📈 Evaluation Results:")
        print("================================")
        print("Overall Accuracy: \(String(format: "%.4f", accuracy)) (\(String(format: "%.2f", accuracy * 100))%)")
        print("Correct Predictions: \(correctPredictions)/\(testCases.count)")
        print("Average Latency: \(String(format: "%.2f", averageLatency)) ms")
        print("P95 Latency: \(String(format: "%.2f", percentile(predictions.map { $0.latency }, 0.95))) ms")
        print("Max Latency: \(String(format: "%.2f", predictions.map { $0.latency }.max() ?? 0)) ms")
        
        // Check performance requirements
        let p95Latency = percentile(predictions.map { $0.latency }, 0.95)
        if p95Latency <= 2.0 {
            print("✅ Latency requirement met (P95 ≤ 2ms)")
        } else {
            print("⚠️  WARNING: P95 latency exceeds 2ms requirement")
        }
        
        if accuracy >= 0.85 {
            print("✅ Accuracy requirement met (≥85%)")
        } else {
            print("⚠️  WARNING: Accuracy below 85% threshold")
        }
        
        // Per-label accuracy
        print("\n📊 Per-Label Performance:")
        for label in labelConfusion.keys.sorted() {
            let labelCounts = labelConfusion[label]!
            let totalForLabel = labelCounts.values.reduce(0, +)
            let correctForLabel = labelCounts[label] ?? 0
            let labelAccuracy = Double(correctForLabel) / Double(totalForLabel)
            
            print("   \(label): \(String(format: "%.3f", labelAccuracy)) (\(correctForLabel)/\(totalForLabel))")
        }
        
        // Show confusion matrix
        print("\n🔀 Confusion Matrix:")
        let allLabels = Array(Set(labelConfusion.keys) ∪ Set(labelConfusion.values.flatMap { $0.keys })).sorted()
        print("Actual\\Predicted\t\(allLabels.joined(separator: "\t"))")
        
        for actualLabel in allLabels {
            var row = [actualLabel]
            for predictedLabel in allLabels {
                let count = labelConfusion[actualLabel]?[predictedLabel] ?? 0
                row.append("\(count)")
            }
            print(row.joined(separator: "\t\t"))
        }
        
        // Show worst predictions (lowest confidence correct predictions and errors)
        print("\n❌ Prediction Errors:")
        let errors = predictions.filter { $0.expected != $0.predicted }.prefix(5)
        for error in errors {
            print("   '\(error.input)' → Expected: \(error.expected), Got: \(error.predicted) (conf: \(String(format: "%.3f", error.confidence)))")
        }
        
        print("\n🔍 Low Confidence Correct Predictions:")
        let lowConfidence = predictions.filter { $0.expected == $0.predicted && $0.confidence < 0.8 }.sorted { $0.confidence < $1.confidence }.prefix(3)
        for pred in lowConfidence {
            print("   '\(pred.input)' → \(pred.predicted) (conf: \(String(format: "%.3f", pred.confidence)))")
        }
        
        print("\n✅ Evaluation completed!")
        
        // Exit with error code if quality gates fail
        if accuracy < 0.85 || p95Latency > 2.0 {
            print("❌ Model failed quality gates")
            exit(1)
        }
        
    } catch {
        print("❌ Error during evaluation: \(error)")
        exit(1)
    }
}

// Helper function to calculate percentiles
func percentile(_ values: [Double], _ p: Double) -> Double {
    let sorted = values.sorted()
    let index = Int(Double(sorted.count - 1) * p)
    return sorted[index]
}

// Entry point
main()