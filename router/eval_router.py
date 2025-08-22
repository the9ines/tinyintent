#!/usr/bin/env python3
"""
TinyIntent Router Evaluation - Python Implementation
Evaluates trained CoreML router model with richer metrics including precision, recall, F1,
confidence calibration (ECE), and reliability analysis.
"""

import json
import time
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import (
    accuracy_score, precision_recall_fscore_support, 
    confusion_matrix, roc_auc_score, average_precision_score
)
from sklearn.calibration import calibration_curve
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_test_data(data_path):
    """Load test data for evaluation"""
    logger.info(f"Loading test data from: {data_path}")
    
    if data_path.suffix == '.csv':
        df = pd.read_csv(data_path)
    else:  # assume TSV
        df = pd.read_csv(data_path, sep='\t')
    
    # Convert labels to numerical
    label_map = {'gen': 0, 'act': 1}
    df['label_id'] = df['label'].map(label_map)
    
    logger.info(f"Loaded {len(df)} test examples")
    return df['text'].tolist(), df['label_id'].tolist(), label_map

def evaluate_coreml_model(model_path, test_texts, test_labels, tokenizer_path=None):
    """Evaluate CoreML model on test data"""
    
    try:
        import coremltools as ct
    except ImportError:
        raise ImportError("coremltools is required. Install with: pip install coremltools")
    
    # Load CoreML model
    logger.info(f"Loading CoreML model: {model_path}")
    model = ct.models.MLModel(str(model_path))
    
    # Load tokenizer for preprocessing
    if tokenizer_path:
        try:
            from transformers import AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
            logger.info(f"Loaded tokenizer from: {tokenizer_path}")
        except Exception as e:
            logger.error(f"Failed to load tokenizer: {e}")
            return None
    else:
        logger.error("No tokenizer path provided")
        return None
    
    # Run predictions
    predictions = []
    confidences = []
    latencies = []
    
    logger.info("Running predictions...")
    
    for i, text in enumerate(test_texts):
        if i % 10 == 0:
            logger.info(f"Processing {i}/{len(test_texts)}")
        
        try:
            start_time = time.time()
            
            # Tokenize input
            inputs = tokenizer(
                text,
                truncation=True,
                padding='max_length',
                max_length=128,
                return_tensors='np'
            )
            
            # Prepare inputs for Core ML
            coreml_inputs = {
                'input_ids': inputs['input_ids'].astype(np.int32),
                'attention_mask': inputs['attention_mask'].astype(np.int32)
            }
            
            # Run inference
            prediction = model.predict(coreml_inputs)
            
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            latencies.append(latency_ms)
            
            # Extract logits (the key might vary)
            logits_key = list(prediction.keys())[0]  # Get first output
            logits = prediction[logits_key]
            
            # Get prediction and confidence
            if len(logits.shape) > 1:
                predicted_class = np.argmax(logits[0])
                # Apply softmax to get probabilities
                probs = np.exp(logits[0]) / np.sum(np.exp(logits[0]))
                confidence = probs[predicted_class]
            else:
                predicted_class = np.argmax(logits)
                confidence = 0.5  # Default confidence
            
            predictions.append(predicted_class)
            confidences.append(confidence)
            
        except Exception as e:
            logger.error(f"Failed to process text '{text[:50]}...': {e}")
            # Use fallback prediction
            predictions.append(0)  # Default to 'gen'
            confidences.append(0.5)
            latencies.append(1000.0)  # Default latency
    
    return np.array(predictions), np.array(confidences), np.array(latencies)

def calculate_calibration_metrics(confidences, predictions, labels):
    """Calculate calibration metrics including ECE"""
    
    # Expected Calibration Error (ECE)
    def calculate_ece(confidences, predictions, labels, n_bins=10):
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        bin_lowers = bin_boundaries[:-1]
        bin_uppers = bin_boundaries[1:]
        
        ece = 0.0
        bin_data = []
        
        for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
            in_bin = (confidences > bin_lower) & (confidences <= bin_upper)
            prop_in_bin = in_bin.mean()
            
            if prop_in_bin > 0:
                accuracy_in_bin = (predictions[in_bin] == labels[in_bin]).mean()
                avg_confidence_in_bin = confidences[in_bin].mean()
                ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
                
                bin_data.append({
                    'bin_lower': float(bin_lower),
                    'bin_upper': float(bin_upper),
                    'bin_accuracy': float(accuracy_in_bin),
                    'bin_confidence': float(avg_confidence_in_bin),
                    'bin_count': int(in_bin.sum()),
                    'proportion': float(prop_in_bin)
                })
            else:
                bin_data.append({
                    'bin_lower': float(bin_lower),
                    'bin_upper': float(bin_upper),
                    'bin_accuracy': 0.0,
                    'bin_confidence': 0.0,
                    'bin_count': 0,
                    'proportion': 0.0
                })
        
        return ece, bin_data
    
    ece, bin_data = calculate_ece(confidences, predictions, labels)
    
    # Reliability diagram data
    try:
        fraction_of_positives, mean_predicted_value = calibration_curve(
            labels, confidences, n_bins=10
        )
        reliability_diagram = {
            'fraction_of_positives': fraction_of_positives.tolist(),
            'mean_predicted_value': mean_predicted_value.tolist()
        }
    except Exception as e:
        logger.warning(f"Could not calculate reliability diagram: {e}")
        reliability_diagram = None
    
    return {
        'ece': float(ece),
        'reliability_diagram': reliability_diagram,
        'calibration_bins': bin_data,
        'mean_confidence': float(confidences.mean()),
        'confidence_std': float(confidences.std())
    }

def evaluate_model_performance(predictions, confidences, test_labels, latencies):
    """Calculate comprehensive performance metrics"""
    
    test_labels = np.array(test_labels)
    
    # Basic metrics
    accuracy = accuracy_score(test_labels, predictions)
    precision, recall, f1, support = precision_recall_fscore_support(
        test_labels, predictions, average=None, zero_division=0
    )
    
    # Per-class metrics
    per_class_metrics = {}
    label_names = ['gen', 'act']
    for i, label in enumerate(label_names):
        per_class_metrics[label] = {
            'precision': float(precision[i]) if i < len(precision) else 0.0,
            'recall': float(recall[i]) if i < len(recall) else 0.0,
            'f1': float(f1[i]) if i < len(f1) else 0.0,
            'support': int(support[i]) if i < len(support) else 0
        }
    
    # Confusion matrix
    cm = confusion_matrix(test_labels, predictions)
    confusion_matrix_dict = {
        'true_negatives': int(cm[0, 0]) if cm.shape == (2, 2) else 0,
        'false_positives': int(cm[0, 1]) if cm.shape == (2, 2) else 0,
        'false_negatives': int(cm[1, 0]) if cm.shape == (2, 2) else 0,
        'true_positives': int(cm[1, 1]) if cm.shape == (2, 2) else 0
    }
    
    # ROC AUC and PR AUC
    try:
        roc_auc = roc_auc_score(test_labels, confidences)
    except Exception:
        roc_auc = None
    
    try:
        pr_auc = average_precision_score(test_labels, confidences)
    except Exception:
        pr_auc = None
    
    # Latency metrics
    avg_latency = float(latencies.mean())
    p95_latency = float(np.percentile(latencies, 95))
    max_latency = float(latencies.max())
    
    # Calibration metrics
    calibration_metrics = calculate_calibration_metrics(confidences, predictions, test_labels)
    
    return {
        'accuracy': float(accuracy),
        'precision_macro': float(precision.mean()),
        'recall_macro': float(recall.mean()),
        'f1_macro': float(f1.mean()),
        'per_class_metrics': per_class_metrics,
        'confusion_matrix': confusion_matrix_dict,
        'roc_auc': roc_auc,
        'pr_auc': pr_auc,
        'latency': {
            'mean_ms': avg_latency,
            'p95_ms': p95_latency,
            'max_ms': max_latency,
            'std_ms': float(latencies.std())
        },
        'calibration': calibration_metrics,
        'sample_count': len(test_labels)
    }

def determine_promotion_eligibility(metrics, thresholds=None):
    """Determine if model meets promotion criteria"""
    
    if thresholds is None:
        thresholds = {
            'min_accuracy': 0.85,
            'max_latency_p95': 50.0,  # 50ms
            'max_ece': 0.15,  # Expected Calibration Error
            'min_f1': 0.80
        }
    
    checks = {
        'accuracy_check': metrics['accuracy'] >= thresholds['min_accuracy'],
        'latency_check': metrics['latency']['p95_ms'] <= thresholds['max_latency_p95'],
        'calibration_check': metrics['calibration']['ece'] <= thresholds['max_ece'],
        'f1_check': metrics['f1_macro'] >= thresholds['min_f1']
    }
    
    promotion_eligible = all(checks.values())
    
    return {
        'promotion_eligible': promotion_eligible,
        'checks': checks,
        'thresholds': thresholds,
        'summary': f"Model {'PASSES' if promotion_eligible else 'FAILS'} promotion criteria"
    }

def main():
    """Main evaluation function"""
    project_root = Path(__file__).parent.parent
    
    # Paths
    model_path = project_root / "router" / "SmallIntent.mlmodel"
    test_data_path = project_root / "router" / "data" / "intents_test.tsv"
    
    # Fallback test data paths
    if not test_data_path.exists():
        test_data_path = project_root / "router" / "data" / "intents.tsv"
    
    if not test_data_path.exists():
        raise FileNotFoundError(f"No test data found at {test_data_path}")
    
    if not model_path.exists():
        raise FileNotFoundError(f"No CoreML model found at {model_path}")
    
    # Tokenizer path
    tokenizer_path = project_root / "router" / "train" / "output" / "final_model"
    if not tokenizer_path.exists():
        # Try alternative output directories
        output_dirs = [
            "train_output",
            "train_enhanced_output", 
            "train_fixed_output",
            "train_improved_output"
        ]
        
        for output_dir in output_dirs:
            alt_path = project_root / "router" / output_dir / "final_model"
            if alt_path.exists():
                tokenizer_path = alt_path
                break
        
        if not tokenizer_path.exists():
            raise FileNotFoundError(f"No tokenizer found. Expected at {tokenizer_path}")
    
    logger.info(f"Using tokenizer from: {tokenizer_path}")
    
    # Load test data
    test_texts, test_labels, label_map = load_test_data(test_data_path)
    
    # Evaluate model
    logger.info("Starting CoreML model evaluation...")
    predictions, confidences, latencies = evaluate_coreml_model(
        model_path, test_texts, test_labels, tokenizer_path
    )
    
    if predictions is None:
        logger.error("Model evaluation failed")
        return False
    
    # Calculate metrics
    logger.info("Calculating performance metrics...")
    metrics = evaluate_model_performance(predictions, confidences, test_labels, latencies)
    
    # Determine promotion eligibility
    promotion_result = determine_promotion_eligibility(metrics)
    
    # Create evaluation result
    eval_result = {
        'timestamp': pd.Timestamp.now().isoformat(),
        'model_path': str(model_path),
        'test_data_path': str(test_data_path),
        'test_sample_count': len(test_labels),
        'label_map': label_map,
        'performance': metrics,
        'promotion': promotion_result,
        'model_info': {
            'size_mb': sum(f.stat().st_size for f in model_path.rglob('*') if f.is_file()) / (1024 * 1024),
            'architecture': 'transformer_classification_coreml'
        }
    }
    
    # Save results
    output_path = project_root / "router" / "data" / "eval_results.json"
    with open(output_path, 'w') as f:
        json.dump(eval_result, f, indent=2)
    
    # Print summary
    logger.info("\n" + "="*50)
    logger.info("EVALUATION SUMMARY")
    logger.info("="*50)
    logger.info(f"Model: {model_path}")
    logger.info(f"Test samples: {len(test_labels)}")
    logger.info(f"Accuracy: {metrics['accuracy']:.4f}")
    logger.info(f"F1 (macro): {metrics['f1_macro']:.4f}")
    logger.info(f"Precision (macro): {metrics['precision_macro']:.4f}")
    logger.info(f"Recall (macro): {metrics['recall_macro']:.4f}")
    logger.info(f"ROC AUC: {metrics['roc_auc']:.4f}" if metrics['roc_auc'] else "ROC AUC: N/A")
    logger.info(f"Latency (P95): {metrics['latency']['p95_ms']:.2f}ms")
    logger.info(f"Latency (mean): {metrics['latency']['mean_ms']:.2f}ms")
    logger.info(f"Calibration (ECE): {metrics['calibration']['ece']:.4f}")
    logger.info("")
    logger.info("Per-class metrics:")
    for label, class_metrics in metrics['per_class_metrics'].items():
        logger.info(f"  {label}: P={class_metrics['precision']:.3f}, R={class_metrics['recall']:.3f}, F1={class_metrics['f1']:.3f}")
    logger.info("")
    logger.info(f"Promotion status: {promotion_result['summary']}")
    logger.info(f"Results saved to: {output_path}")
    
    return promotion_result['promotion_eligible']

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)