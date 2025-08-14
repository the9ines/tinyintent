import Foundation
import CoreML

// TinyIntent runtime: loads a Core ML model (.mlpackage or .mlmodel),
// compiles it to .mlmodelc if needed, and prints ONLY the predicted label.
// If the model expects tokenized tensors (not raw text), print a clear error.

enum TIError: Error {
  case emptyInput
  case modelNotFound
  case loadFailed(String)
  case incompatibleModel(String) // e.g., tensor inputs without tokenizer
}

func stderr(_ s: String) {
  FileHandle.standardError.write((s + "\n").data(using: .utf8)!)
}

// Try env override first, then the canonical paths (.mlpackage → .mlmodel).
func findModelURL() -> URL? {
  let fm = FileManager.default
  if let override = ProcessInfo.processInfo.environment["TINYINTENT_MODEL"], !override.isEmpty {
    let u = URL(fileURLWithPath: override)
    if fm.fileExists(atPath: u.path) { return u }
  }
  // Canonical lower-case path
  let root = "/Users/oberfelder/projects/smallintent/router"
  let candidates = [
    URL(fileURLWithPath: root).appendingPathComponent("TinyIntent.mlpackage"),
    URL(fileURLWithPath: root).appendingPathComponent("TinyIntent.mlmodel"),
    // Safety: if any file ended up under 'Projects' (capital P)
    URL(fileURLWithPath: "/Users/oberfelder/Projects/smallintent/router/TinyIntent.mlpackage"),
    URL(fileURLWithPath: "/Users/oberfelder/Projects/smallintent/router/TinyIntent.mlmodel"),
  ]
  for c in candidates where fm.fileExists(atPath: c.path) {
    return c
  }
  return nil
}

func compileIfNeeded(_ url: URL) throws -> URL {
  // If it's already a compiled bundle (.mlmodelc) just use it.
  if url.pathExtension == "mlmodelc" { return url }
  // Otherwise compile to a temp location.
  return try MLModel.compileModel(at: url)
}

func loadModel() throws -> MLModel {
  guard let rawURL = findModelURL() else {
    throw TIError.modelNotFound
  }
  let compiledURL = try compileIfNeeded(rawURL)
  let cfg = MLModelConfiguration()
  cfg.computeUnits = .cpuAndNeuralEngine
  do {
    return try MLModel(contentsOf: compiledURL, configuration: cfg)
  } catch {
    throw TIError.loadFailed(error.localizedDescription)
  }
}

func readInputText() throws -> String {
  let args = CommandLine.arguments.dropFirst()
  if let first = args.first, !first.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
    return first
  }
  // Read stdin until EOF
  let data = FileHandle.standardInput.readDataToEndOfFile()
  let txt = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
  if txt.isEmpty { throw TIError.emptyInput }
  return txt
}

func main() {
  do {
    let text = try readInputText()
    let model = try loadModel()

    // Inspect model input names. If it doesn't accept raw "text" or "string" input,
    // we can't tokenize here (no vocab bundled). Emit clear guidance and exit 2.
    let spec = model.modelDescription
    let inputNames = spec.inputDescriptionsByName.keys.map { String($0) }.sorted()

    // Heuristic: text-classifier models typically expose a String input (e.g. "text").
    let supportsRawText = inputNames.contains { name in
      if let d = spec.inputDescriptionsByName[name],
         d.type == .string {
        return true
      }
      return false
    }

    guard supportsRawText else {
      stderr("Error: This model expects tokenized tensors (e.g., input_ids/attention_mask) and cannot consume raw text.")
      stderr("Hint: Use ROUTE env (from iPhone Shortcut) or set TINYINTENT_MODEL to a CreateML-style text classifier.")
      exit(2)
    }

    // Build features with the first String input name.
    let textInputName: String = {
      for name in inputNames {
        if let d = spec.inputDescriptionsByName[name], d.type == .string { return name }
      }
      return "text"
    }()

    let provider = try MLDictionaryFeatureProvider(dictionary: [textInputName: text] as [String: Any])
    let out = try model.prediction(from: provider)

    // Common label keys to probe: "classLabel", "label", "predictedLabel"
    let labelKeys = ["classLabel", "label", "predictedLabel"]
    for k in labelKeys {
      if let v = out.featureValue(for: k)?.stringValue, !v.isEmpty {
        print(v) // ONLY the label + newline
        return
      }
    }

    // As a fallback, if the output contains a single string, print it.
    for (k, v) in out.featureNames.map({ ($0, out.featureValue(for: $0)) }) {
      if let s = v?.stringValue, !s.isEmpty {
        print(s)
        return
      }
    }

    stderr("Error: could not find a string label in model outputs: \(Array(out.featureNames))")
    exit(3)

  } catch TIError.emptyInput {
    stderr("Error: empty input. Pass text as an argument or via stdin.")
    exit(1)
  } catch TIError.modelNotFound {
    stderr("Error: model not found. Set TINYINTENT_MODEL or place TinyIntent.mlpackage/mlmodel under router/")
    exit(1)
  } catch TIError.loadFailed(let msg) {
    stderr("Error: failed to load model: \(msg)")
    exit(1)
  } catch {
    stderr("Error: \(error)")
    exit(1)
  }
}

main()