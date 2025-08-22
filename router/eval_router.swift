#!/usr/bin/env swift

/*
TinyIntent Router Evaluation - M7.1: Router Quality, Thresholds & Fallbacks

Evaluates trained router model with richer metrics including precision, recall, F1,
confidence calibration (ECE), and reliability analysis.
*/

import Foundation
import CoreML

struct EvaluationResult: Codable {
    let accuracy: Double
    let precision: Double
    let recall: Double
    let f1: Double
    let per_class_metrics: [String: ClassMetrics]
    let confusion_matrix: ConfusionMatrix
    let roc_auc: Double?
    let pr_auc: Double?
    let latency_ms: Double
    let sample_count: Int
    let timestamp: String
    let model_path: String
    let test_data_path: String
    let promotion_eligible: Bool
    let accuracy_threshold: Double
    let latency_threshold: Double
    let calibration: CalibrationMetrics
}

struct ClassMetrics: Codable {
    let precision: Double
    let recall: Double
    let f1: Double
    let support: Int
}

struct ConfusionMatrix: Codable {
    let labels: [String]
    let matrix: [[Int]]
}

struct CalibrationMetrics: Codable {
    let ece: Double  // Expected Calibration Error
    let reliability_bins: [ReliabilityBin]
}

struct ReliabilityBin: Codable {
    let bin_lower: Double
    let bin_upper: Double
    let avg_conf: Double
    let emp_acc: Double
    let count: Int
}

struct TestSample {
    let text: String
    let expectedLabel: String
}

struct PredictionResult {
    let predictedLabel: String
    let confidence: Double
    let allConfidences: [String: Double]
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
        
        // Run evaluation with detailed predictions
        var predictions: [PredictionResult] = []
        var totalLatency: TimeInterval = 0
        
        for (index, sample) in testSamples.enumerated() {
            let startTime = Date()
            
            // Make prediction with confidence scores
            if let prediction = predictWithConfidence(model: model, text: sample.text) {
                let endTime = Date()
                let sampleLatency = endTime.timeIntervalSince(startTime) * 1000 // Convert to ms
                totalLatency += sampleLatency
                
                predictions.append(prediction)
                
                // Progress indicator
                if (index + 1) % 10 == 0 {
                    print("   Processed \(index + 1)/\(testSamples.count) samples...")
                }
            } else {
                print("⚠️  Failed to predict for sample \(index + 1)")
            }
        }
        
        guard predictions.count == testSamples.count else {
            print("❌ Some predictions failed")
            return nil
        }
        
        // Calculate comprehensive metrics
        let accuracy = calculateAccuracy(testSamples: testSamples, predictions: predictions)
        let avgLatency = totalLatency / Double(testSamples.count)
        
        // Calculate precision, recall, F1
        let allLabels = Array(Set(testSamples.map { $0.expectedLabel })).sorted()
        let (precision, recall, f1, perClassMetrics) = calculateClassificationMetrics(
            testSamples: testSamples, predictions: predictions, labels: allLabels)
        
        // Calculate confusion matrix
        let confusionMatrix = calculateConfusionMatrix(
            testSamples: testSamples, predictions: predictions, labels: allLabels)
        
        // Calculate ROC AUC and PR AUC (for binary classification)
        let rocAuc = allLabels.count == 2 ? calculateROCAUC(
            testSamples: testSamples, predictions: predictions, labels: allLabels) : nil
        let prAuc = allLabels.count == 2 ? calculatePRAUC(
            testSamples: testSamples, predictions: predictions, labels: allLabels) : nil
        
        // Calculate confidence calibration metrics
        let calibrationMetrics = calculateCalibrationMetrics(
            testSamples: testSamples, predictions: predictions)
        
        // Save reliability curve CSV
        saveReliabilityCurve(calibrationMetrics.reliability_bins)
        
        let promotionEligible = accuracy >= accuracyThreshold && avgLatency <= latencyThreshold
        
        // Create result
        let result = EvaluationResult(
            accuracy: accuracy,
            precision: precision,
            recall: recall,
            f1: f1,
            per_class_metrics: perClassMetrics,
            confusion_matrix: confusionMatrix,
            roc_auc: rocAuc,
            pr_auc: prAuc,
            latency_ms: avgLatency,
            sample_count: testSamples.count,
            timestamp: ISO8601DateFormatter().string(from: Date()),
            model_path: modelPath,
            test_data_path: testDataPath,
            promotion_eligible: promotionEligible,
            accuracy_threshold: accuracyThreshold,
            latency_threshold: latencyThreshold,
            calibration: calibrationMetrics
        )
        
        // Print comprehensive results
        printResults(result: result, labels: allLabels)
        
        return result
    }
    
    private func predictWithConfidence(model: MLModel, text: String) -> PredictionResult? {
        do {
            // Create input features
            let inputFeatures = try MLDictionaryFeatureProvider(dictionary: ["text": text])
            
            // Make prediction
            let prediction = try model.prediction(from: inputFeatures)
            
            var predictedLabel = "gen"  // default
            var allConfidences: [String: Double] = [:]
            var maxConfidence = 0.5
            
            // Try to get confidence scores
            if let confidenceDict = prediction.featureValue(for: "classProbability")?.dictionaryValue {
                for (label, prob) in confidenceDict {
                    if let labelStr = label as? String, let probVal = prob as? Double {
                        allConfidences[labelStr] = probVal
                        if probVal > maxConfidence {
                            maxConfidence = probVal
                            predictedLabel = labelStr
                        }
                    }
                }
            }
            
            // Fallback: try to get direct label prediction
            if let labelFeature = prediction.featureValue(for: "label") {
                if let directLabel = labelFeature.stringValue {
                    predictedLabel = directLabel
                }
            } else if let labelFeature = prediction.featureValue(for: "classLabel") {
                if let directLabel = labelFeature.stringValue {
                    predictedLabel = directLabel
                }
            }
            
            return PredictionResult(
                predictedLabel: predictedLabel,
                confidence: maxConfidence,
                allConfidences: allConfidences
            )
            
        } catch {
            print("⚠️  Prediction error: \(error)")
            return nil
        }
    }
    
    private func calculateAccuracy(testSamples: [TestSample], predictions: [PredictionResult]) -> Double {
        let correctPredictions = zip(testSamples, predictions).reduce(0) { count, pair in
            count + (pair.0.expectedLabel.lowercased() == pair.1.predictedLabel.lowercased() ? 1 : 0)
        }
        return Double(correctPredictions) / Double(testSamples.count) * 100.0
    }
    
    private func calculateClassificationMetrics(testSamples: [TestSample], predictions: [PredictionResult], labels: [String]) -> (Double, Double, Double, [String: ClassMetrics]) {
        var truePositives: [String: Int] = [:]
        var falsePositives: [String: Int] = [:]
        var falseNegatives: [String: Int] = [:]
        var support: [String: Int] = [:]
        
        // Initialize counts
        for label in labels {
            truePositives[label] = 0
            falsePositives[label] = 0
            falseNegatives[label] = 0
            support[label] = 0
        }
        
        // Count TP, FP, FN
        for (testSample, prediction) in zip(testSamples, predictions) {
            let actual = testSample.expectedLabel.lowercased()
            let predicted = prediction.predictedLabel.lowercased()
            
            support[actual, default: 0] += 1
            
            if actual == predicted {
                truePositives[actual, default: 0] += 1
            } else {
                falseNegatives[actual, default: 0] += 1
                falsePositives[predicted, default: 0] += 1
            }
        }
        
        // Calculate per-class metrics
        var perClassMetrics: [String: ClassMetrics] = [:]
        var weightedPrecision = 0.0
        var weightedRecall = 0.0
        var weightedF1 = 0.0
        var totalSupport = 0
        
        for label in labels {
            let tp = truePositives[label, default: 0]
            let fp = falsePositives[label, default: 0]
            let fn = falseNegatives[label, default: 0]
            let sup = support[label, default: 0]
            
            let precision = tp + fp > 0 ? Double(tp) / Double(tp + fp) : 0.0
            let recall = tp + fn > 0 ? Double(tp) / Double(tp + fn) : 0.0
            let f1 = (precision + recall) > 0 ? 2 * (precision * recall) / (precision + recall) : 0.0
            
            perClassMetrics[label] = ClassMetrics(
                precision: precision * 100.0,
                recall: recall * 100.0,
                f1: f1 * 100.0,
                support: sup
            )
            
            // Weighted averages
            weightedPrecision += precision * Double(sup)
            weightedRecall += recall * Double(sup)
            weightedF1 += f1 * Double(sup)
            totalSupport += sup
        }
        
        let avgPrecision = totalSupport > 0 ? (weightedPrecision / Double(totalSupport)) * 100.0 : 0.0
        let avgRecall = totalSupport > 0 ? (weightedRecall / Double(totalSupport)) * 100.0 : 0.0
        let avgF1 = totalSupport > 0 ? (weightedF1 / Double(totalSupport)) * 100.0 : 0.0
        
        return (avgPrecision, avgRecall, avgF1, perClassMetrics)
    }
    
    private func calculateConfusionMatrix(testSamples: [TestSample], predictions: [PredictionResult], labels: [String]) -> ConfusionMatrix {
        var matrix: [[Int]] = Array(repeating: Array(repeating: 0, count: labels.count), count: labels.count)
        
        for (testSample, prediction) in zip(testSamples, predictions) {
            let actual = testSample.expectedLabel.lowercased()
            let predicted = prediction.predictedLabel.lowercased()
            
            if let actualIdx = labels.firstIndex(of: actual),
               let predictedIdx = labels.firstIndex(of: predicted) {
                matrix[actualIdx][predictedIdx] += 1
            }
        }
        
        return ConfusionMatrix(labels: labels, matrix: matrix)
    }
    
    private func calculateROCAUC(testSamples: [TestSample], predictions: [PredictionResult], labels: [String]) -> Double? {
        // Simplified ROC AUC calculation for binary classification
        guard labels.count == 2 else { return nil }
        
        let positiveLabel = labels[1]  // Assume second label is positive
        var scores: [(Double, Bool)] = []
        
        for (testSample, prediction) in zip(testSamples, predictions) {
            let isPositive = testSample.expectedLabel.lowercased() == positiveLabel.lowercased()
            scores.append((prediction.confidence, isPositive))
        }
        
        scores.sort { $0.0 > $1.0 }  // Sort by confidence descending
        
        var auc = 0.0
        var tp = 0
        var fp = 0
        let totalPositives = scores.reduce(0) { $0 + ($1.1 ? 1 : 0) }
        let totalNegatives = scores.count - totalPositives
        
        guard totalPositives > 0 && totalNegatives > 0 else { return nil }
        
        for (_, isPositive) in scores {
            if isPositive {
                tp += 1
            } else {
                fp += 1
                auc += Double(tp)
            }
        }
        
        return auc / (Double(totalPositives) * Double(totalNegatives))
    }
    
    private func calculatePRAUC(testSamples: [TestSample], predictions: [PredictionResult], labels: [String]) -> Double? {
        // Simplified PR AUC calculation for binary classification
        guard labels.count == 2 else { return nil }
        
        let positiveLabel = labels[1]
        var scores: [(Double, Bool)] = []
        
        for (testSample, prediction) in zip(testSamples, predictions) {
            let isPositive = testSample.expectedLabel.lowercased() == positiveLabel.lowercased()
            scores.append((prediction.confidence, isPositive))
        }
        
        scores.sort { $0.0 > $1.0 }
        
        var auc = 0.0
        var tp = 0
        var fp = 0
        let totalPositives = scores.reduce(0) { $0 + ($1.1 ? 1 : 0) }
        
        guard totalPositives > 0 else { return nil }
        
        var prevRecall = 0.0
        
        for (_, isPositive) in scores {
            if isPositive {
                tp += 1
            } else {
                fp += 1
            }
            
            let recall = Double(tp) / Double(totalPositives)
            let precision = Double(tp) / Double(tp + fp)
            
            auc += precision * (recall - prevRecall)
            prevRecall = recall
        }
        
        return auc
    }
    
    private func calculateCalibrationMetrics(testSamples: [TestSample], predictions: [PredictionResult]) -> CalibrationMetrics {
        let numBins = 10
        var bins: [ReliabilityBin] = []
        
        // Sort predictions by confidence
        let sortedPairs = zip(testSamples, predictions).sorted { $0.1.confidence < $1.1.confidence }
        
        // Create bins
        for binIdx in 0..<numBins {
            let binLower = Double(binIdx) / Double(numBins)
            let binUpper = Double(binIdx + 1) / Double(numBins)
            
            let binSamples = sortedPairs.filter { pair in
                let conf = pair.1.confidence
                return conf >= binLower && conf < binUpper || (binIdx == numBins - 1 && conf >= binLower)
            }
            
            guard !binSamples.isEmpty else {
                bins.append(ReliabilityBin(
                    bin_lower: binLower,
                    bin_upper: binUpper,
                    avg_conf: 0.0,
                    emp_acc: 0.0,
                    count: 0
                ))
                continue
            }
            
            let avgConf = binSamples.reduce(0.0) { $0 + $1.1.confidence } / Double(binSamples.count)
            let correct = binSamples.reduce(0) { count, pair in
                count + (pair.0.expectedLabel.lowercased() == pair.1.predictedLabel.lowercased() ? 1 : 0)
            }
            let empAcc = Double(correct) / Double(binSamples.count)
            
            bins.append(ReliabilityBin(
                bin_lower: binLower,
                bin_upper: binUpper,
                avg_conf: avgConf,
                emp_acc: empAcc,
                count: binSamples.count
            ))
        }
        
        // Calculate Expected Calibration Error (ECE)
        let totalSamples = Double(testSamples.count)
        let ece = bins.reduce(0.0) { sum, bin in
            let weight = Double(bin.count) / totalSamples
            return sum + weight * abs(bin.avg_conf - bin.emp_acc)
        }
        
        return CalibrationMetrics(ece: ece, reliability_bins: bins)
    }
    
    private func saveReliabilityCurve(_ bins: [ReliabilityBin]) {
        let outputPath = URL(fileURLWithPath: modelPath).deletingLastPathComponent()
            .appendingPathComponent("data")
            .appendingPathComponent("reliability_curve.csv")
        
        var csvContent = "bin_lower,bin_upper,avg_conf,emp_acc,count\n"
        for bin in bins {
            csvContent += "\(bin.bin_lower),\(bin.bin_upper),\(bin.avg_conf),\(bin.emp_acc),\(bin.count)\n"
        }
        
        do {
            try csvContent.write(to: outputPath, atomically: true, encoding: .utf8)
            print("💾 Reliability curve saved to: \(outputPath.path)")
        } catch {
            print("⚠️  Failed to save reliability curve: \(error)")
        }
    }
    
    private func printResults(result: EvaluationResult, labels: [String]) {
        print("\n📈 Comprehensive Evaluation Results:")
        print("   Accuracy: \(String(format: "%.2f", result.accuracy))%")
        print("   Precision: \(String(format: "%.2f", result.precision))%")
        print("   Recall: \(String(format: "%.2f", result.recall))%")
        print("   F1-Score: \(String(format: "%.2f", result.f1))%")
        print("   Avg Latency: \(String(format: "%.2f", result.latency_ms))ms")
        print("   Sample Count: \(result.sample_count)")
        
        if let rocAuc = result.roc_auc {
            print("   ROC AUC: \(String(format: "%.4f", rocAuc))")
        }
        if let prAuc = result.pr_auc {
            print("   PR AUC: \(String(format: "%.4f", prAuc))")
        }
        
        print("\n📏 Confidence Calibration:")
        print("   Expected Calibration Error (ECE): \(String(format: "%.4f", result.calibration.ece))")
        print("   Reliability Bins: \(result.calibration.reliability_bins.count)")
        
        print("\n📊 Per-Class Metrics:")
        for label in labels {
            if let metrics = result.per_class_metrics[label] {
                print("   \(label): P=\(String(format: "%.2f", metrics.precision))% " +
                      "R=\(String(format: "%.2f", metrics.recall))% " +
                      "F1=\(String(format: "%.2f", metrics.f1))% " +
                      "Support=\(metrics.support)")
            }
        }
        
        print("\n🎯 Promotion Status: \(result.promotion_eligible ? "✅ ELIGIBLE" : "❌ NOT ELIGIBLE")")
        if !result.promotion_eligible {
            if result.accuracy < result.accuracy_threshold {
                print("   - Accuracy too low: \(String(format: "%.2f", result.accuracy))% < \(result.accuracy_threshold)%")
            }
            if result.latency_ms > result.latency_threshold {
                print("   - Latency too high: \(String(format: "%.2f", result.latency_ms))ms > \(result.latency_threshold)ms")
            }
        }
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
            print("💾 Comprehensive evaluation results saved to: \(outputPath)")
            return true
        } catch {
            print("❌ Failed to save results: \(error)")
            return false
        }
    }
}

// Main execution
func main() {
    print("🎯 TinyIntent Router Comprehensive Evaluation - M7.1")
    print("==================================================")
    
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
    
    print("\n🎉 Comprehensive evaluation completed successfully!")
}

main()