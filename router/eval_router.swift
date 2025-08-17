#!/usr/bin/env swift

/*
TinyIntent Router Evaluation - M5.4: Evaluation & Promotion Workflow

Evaluates trained router model for accuracy and latency.
Outputs machine-parseable JSON results for promotion decisions.
*/

import Foundation
import CoreML

struct EvaluationResult: Codable {
    let accuracy: Double
    let latency_ms: Double
    let sample_count: Int
    let timestamp: String
    let model_path: String
    let test_data_path: String
    let promotion_eligible: Bool
    let accuracy_threshold: Double
    let latency_threshold: Double
}

struct TestSample {
    let text: String
    let expectedLabel: String
}

class RouterEvaluator {
    private let modelPath: String
    private let testDataPath: String
    private let accuracyThreshold: Double = 90.0
    private let latencyThreshold: Double = 50.0
    
    init(modelPath: String, testDataPath: String) {
        self.modelPath = modelPath
        self.testDataPath = testDataPath
    }
    
    func evaluateModel() -> EvaluationResult? {
        print("🔍 Loading model from: \(modelPath)")
        
        // Load Core ML model
        guard let model = try? MLModel(contentsOf: URL(fileURLWithPath: modelPath)) else {
            print("❌ Failed to load model from \(modelPath)")
            return nil
        }
        
        print("📊 Loading test data from: \(testDataPath)")
        
        // Load test data
        let testSamples = loadTestData()
        guard !testSamples.isEmpty else {
            print("❌ No test data found")
            return nil
        }
        
        print("🚀 Evaluating \(testSamples.count) samples...")
        
        // Run evaluation
        var correctPredictions = 0
        var totalLatency: TimeInterval = 0
        
        for (index, sample) in testSamples.enumerated() {
            let startTime = Date()
            
            // Make prediction
            if let prediction = predict(model: model, text: sample.text) {
                let endTime = Date()
                let sampleLatency = endTime.timeIntervalSince(startTime) * 1000 // Convert to ms
                totalLatency += sampleLatency
                
                // Check accuracy
                if prediction.lowercased() == sample.expectedLabel.lowercased() {
                    correctPredictions += 1
                }
                
                // Progress indicator
                if (index + 1) % 10 == 0 {
                    print("   Processed \(index + 1)/\(testSamples.count) samples...")
                }
            } else {
                print("⚠️  Failed to predict for sample \(index + 1)")
            }
        }
        
        // Calculate metrics
        let accuracy = (Double(correctPredictions) / Double(testSamples.count)) * 100.0
        let avgLatency = totalLatency / Double(testSamples.count)
        let promotionEligible = accuracy >= accuracyThreshold && avgLatency <= latencyThreshold
        
        // Create result
        let result = EvaluationResult(
            accuracy: accuracy,
            latency_ms: avgLatency,
            sample_count: testSamples.count,
            timestamp: ISO8601DateFormatter().string(from: Date()),
            model_path: modelPath,
            test_data_path: testDataPath,
            promotion_eligible: promotionEligible,
            accuracy_threshold: accuracyThreshold,
            latency_threshold: latencyThreshold
        )
        
        // Print results
        print("\n📈 Evaluation Results:")
        print("   Accuracy: \(String(format: "%.2f", accuracy))% (threshold: \(accuracyThreshold)%)")
        print("   Avg Latency: \(String(format: "%.2f", avgLatency))ms (threshold: \(latencyThreshold)ms)")
        print("   Sample Count: \(testSamples.count)")
        print("   Promotion Eligible: \(promotionEligible ? "✅ YES" : "❌ NO")")
        
        return result
    }
    
    private func predict(model: MLModel, text: String) -> String? {
        do {
            // Create input features
            let inputFeatures = try MLDictionaryFeatureProvider(dictionary: ["text": text])
            
            // Make prediction
            let prediction = try model.prediction(from: inputFeatures)
            
            // Extract predicted label
            if let labelFeature = prediction.featureValue(for: "label") {
                return labelFeature.stringValue
            } else if let labelFeature = prediction.featureValue(for: "classLabel") {
                return labelFeature.stringValue
            } else {
                // Try to get the first string output
                let outputNames = model.modelDescription.outputDescriptionsByName.keys
                for outputName in outputNames {
                    if let feature = prediction.featureValue(for: outputName),
                       let stringValue = feature.stringValue {
                        return stringValue
                    }
                }
            }
        } catch {
            print("⚠️  Prediction error: \(error)")
        }
        
        return nil
    }
    
    private func loadTestData() -> [TestSample] {
        guard let data = try? String(contentsOfFile: testDataPath) else {
            print("❌ Failed to read test data file")
            return []
        }
        
        var samples: [TestSample] = []
        let lines = data.components(separatedBy: .newlines)
        
        for (index, line) in lines.enumerated() {
            let trimmedLine = line.trimmingCharacters(in: .whitespacesAndNewlines)
            
            // Skip empty lines and header
            if trimmedLine.isEmpty || index == 0 {
                continue
            }
            
            let components = trimmedLine.components(separatedBy: "\t")
            if components.count >= 2 {
                let text = components[0].trimmingCharacters(in: .whitespacesAndNewlines)
                let label = components[1].trimmingCharacters(in: .whitespacesAndNewlines)
                
                if !text.isEmpty && !label.isEmpty {
                    samples.append(TestSample(text: text, expectedLabel: label))
                }
            }
        }
        
        return samples
    }
    
    func saveResults(_ result: EvaluationResult, to outputPath: String) -> Bool {
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let jsonData = try encoder.encode(result)
            
            try jsonData.write(to: URL(fileURLWithPath: outputPath))
            print("💾 Evaluation results saved to: \(outputPath)")
            return true
        } catch {
            print("❌ Failed to save results: \(error)")
            return false
        }
    }
}

// Main execution
func main() {
    print("🎯 TinyIntent Router Evaluation")
    print("==============================")
    
    // Determine project root
    let currentDir = FileManager.default.currentDirectoryPath
    let projectRoot = URL(fileURLWithPath: currentDir)
    
    // Model paths
    let trainedModelPath = projectRoot
        .appendingPathComponent("router")
        .appendingPathComponent("SmallIntent.mlpackage")
        .path
    
    // Test data path
    let testDataPath = projectRoot
        .appendingPathComponent("router")
        .appendingPathComponent("data")
        .appendingPathComponent("intents_test.tsv")
    
    // Fallback to main training data if test data doesn't exist
    let fallbackTestDataPath = projectRoot
        .appendingPathComponent("router")
        .appendingPathComponent("data")
        .appendingPathComponent("intents.tsv")
    
    let finalTestDataPath = FileManager.default.fileExists(atPath: testDataPath) 
        ? testDataPath 
        : fallbackTestDataPath
    
    // Output path
    let outputPath = projectRoot
        .appendingPathComponent("router")
        .appendingPathComponent("data")
        .appendingPathComponent("eval_results.json")
        .path
    
    // Check if model exists
    guard FileManager.default.fileExists(atPath: trainedModelPath) else {
        print("❌ Model not found at: \(trainedModelPath)")
        print("   Run 'make router-train' first to train the model")
        exit(1)
    }
    
    // Check if test data exists
    guard FileManager.default.fileExists(atPath: finalTestDataPath) else {
        print("❌ Test data not found at: \(finalTestDataPath)")
        print("   Ensure training data exists")
        exit(1)
    }
    
    // Create evaluator and run evaluation
    let evaluator = RouterEvaluator(
        modelPath: trainedModelPath,
        testDataPath: finalTestDataPath
    )
    
    guard let result = evaluator.evaluateModel() else {
        print("❌ Evaluation failed")
        exit(1)
    }
    
    // Save results
    guard evaluator.saveResults(result, to: outputPath) else {
        print("❌ Failed to save evaluation results")
        exit(1)
    }
    
    print("\n🎉 Evaluation completed successfully!")
    
    if result.promotion_eligible {
        print("✅ Model meets promotion criteria")
    } else {
        print("❌ Model does not meet promotion criteria:")
        if result.accuracy < result.accuracy_threshold {
            print("   - Accuracy too low: \(String(format: "%.2f", result.accuracy))% < \(result.accuracy_threshold)%")
        }
        if result.latency_ms > result.latency_threshold {
            print("   - Latency too high: \(String(format: "%.2f", result.latency_ms))ms > \(result.latency_threshold)ms")
        }
    }
}

main()