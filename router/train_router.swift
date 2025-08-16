#!/usr/bin/env swift

import Foundation
import CreateML
import CoreML

/// TinyIntent Router Training Script
/// Trains a MaxEnt classifier for ANE compatibility using CreateML
/// Target model size: ≤16MB for macOS SmallIntent.mlmodel

func main() {
    print("🚀 TinyIntent Router Training - M3")
    print("=====================================")
    
    // Configuration
    let projectRoot = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    let dataPath = projectRoot.appendingPathComponent("router/data/intents.tsv")
    let modelOutputPath = projectRoot.appendingPathComponent("router/SmallIntent.mlmodel")
    
    print("📊 Data source: \(dataPath.path)")
    print("🎯 Model output: \(modelOutputPath.path)")
    
    do {
        // Load training data
        print("\n📁 Loading training data...")
        let dataTable = try MLDataTable(contentsOf: dataPath)
        
        print("✓ Loaded \(dataTable.rows.count) training examples")
        
        // Check data distribution
        let labelCounts = dataTable.rows.compactMap { row -> String? in
            return row["label"]?.stringValue
        }.reduce(into: [String: Int]()) { counts, label in
            counts[label, default: 0] += 1
        }
        
        print("📈 Label distribution:")
        for (label, count) in labelCounts.sorted(by: { $0.key < $1.key }) {
            print("   \(label): \(count) examples")
        }
        
        // Split data into training and validation sets (80/20 split)
        let splitData = dataTable.randomSplit(by: [0.8, 0.2], seed: 42)
        let trainingData = splitData[0]
        let validationData = splitData[1]
        
        print("\n🔄 Data split:")
        print("   Training: \(trainingData.rows.count) examples")
        print("   Validation: \(validationData.rows.count) examples")
        
        // Configure text classifier for maximum efficiency and ANE compatibility
        print("\n🧠 Training MaxEnt classifier...")
        print("   Algorithm: Maximum Entropy (for ANE compatibility)")
        print("   Target size: ≤16MB")
        
        let classifier = try MLTextClassifier(
            trainingData: trainingData,
            textColumn: "text",
            labelColumn: "label",
            parameters: MLTextClassifier.ModelParameters(
                algorithm: .maxEnt,  // Maximum Entropy for ANE compatibility
                revision: .textClassifierRevision1,
                language: .english,
                validationData: validationData
            )
        )
        
        // Evaluate the model
        print("\n📊 Model Evaluation:")
        let trainingAccuracy = classifier.trainingMetrics.classificationError
        let validationAccuracy = classifier.validationMetrics.classificationError
        
        print("   Training Error: \(String(format: "%.4f", trainingAccuracy))")
        print("   Training Accuracy: \(String(format: "%.4f", 1.0 - trainingAccuracy))")
        print("   Validation Error: \(String(format: "%.4f", validationAccuracy))")
        print("   Validation Accuracy: \(String(format: "%.4f", 1.0 - validationAccuracy))")
        
        // Check validation accuracy threshold
        let validationAccuracyPercent = (1.0 - validationAccuracy) * 100
        print("   Validation Accuracy: \(String(format: "%.2f", validationAccuracyPercent))%")
        
        if validationAccuracyPercent < 85.0 {
            print("⚠️  WARNING: Validation accuracy below 85% threshold")
        } else {
            print("✅ Validation accuracy meets quality threshold")
        }
        
        // Save the model
        print("\n💾 Saving model...")
        try classifier.write(to: modelOutputPath)
        
        // Check model size
        let modelSize = try FileManager.default.attributesOfItem(atPath: modelOutputPath.path)[.size] as! Int64
        let modelSizeMB = Double(modelSize) / (1024 * 1024)
        
        print("📏 Model size: \(String(format: "%.2f", modelSizeMB)) MB")
        
        if modelSizeMB > 16.0 {
            print("❌ ERROR: Model size exceeds 16MB limit")
            exit(1)
        } else {
            print("✅ Model size meets 16MB constraint")
        }
        
        // Test model predictions
        print("\n🧪 Testing model predictions:")
        let testInputs = [
            "Generate a summary report",
            "Close all trading positions",
            "Write me a poem",
            "Restart the server"
        ]
        
        for input in testInputs {
            if let prediction = try? classifier.prediction(from: input) {
                let confidence = prediction.classLabelProbs[prediction.classLabel] ?? 0.0
                print("   '\(input)' → \(prediction.classLabel) (confidence: \(String(format: "%.3f", confidence)))")
            }
        }
        
        print("\n🎉 Training completed successfully!")
        print("   Model saved to: \(modelOutputPath.path)")
        print("   Ready for integration with TinyIntent Bridge")
        
    } catch {
        print("❌ Error during training: \(error)")
        exit(1)
    }
}

// Entry point
main()