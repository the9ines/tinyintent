#!/usr/bin/env python3
"""
TinyIntent Router Training Pipeline
Fine-tunes DigiBERT for intent classification (gen vs act)
"""

import os
import pandas as pd
import torch
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from transformers import (
    AutoTokenizer, AutoModelForSequenceClassification,
    TrainingArguments, Trainer, EarlyStoppingCallback
)
from torch.utils.data import Dataset
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IntentDataset(Dataset):
    """Custom dataset for intent classification"""
    
    def __init__(self, texts, labels, tokenizer, max_length=128):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length
    
    def __len__(self):
        return len(self.texts)
    
    def __getitem__(self, idx):
        text = str(self.texts[idx])
        label = self.labels[idx]
        
        encoding = self.tokenizer(
            text,
            truncation=True,
            padding='max_length',
            max_length=self.max_length,
            return_tensors='pt'
        )
        
        return {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'labels': torch.tensor(label, dtype=torch.long)
        }

def load_data(data_path):
    """Load and preprocess the intent data"""
    logger.info(f"Loading data from {data_path}")
    
    # Try different formats
    if data_path.suffix == '.csv':
        df = pd.read_csv(data_path)
    else:  # assume TSV
        df = pd.read_csv(data_path, sep='\t')
    
    logger.info(f"Loaded {len(df)} examples")
    logger.info(f"Columns: {df.columns.tolist()}")
    
    # Check label distribution
    label_counts = df['label'].value_counts()
    logger.info(f"Label distribution:\n{label_counts}")
    
    # Convert labels to numerical
    label_map = {'gen': 0, 'act': 1}
    df['label_id'] = df['label'].map(label_map)
    
    return df, label_map

def setup_model_and_tokenizer(model_name="microsoft/DialoGPT-small"):
    """Setup tokenizer and model for sequence classification"""
    logger.info(f"Loading model: {model_name}")
    
    # Try DigiBERT-like models, fallback to smaller alternatives
    model_options = [
        "google/electra-small-discriminator",  # Small ELECTRA model
        "distilbert-base-uncased",             # DistilBERT
        "microsoft/DialoGPT-small",            # DialoGPT small
        "prajjwal1/bert-tiny"                  # Tiny BERT
    ]
    
    tokenizer = None
    model = None
    
    for model_name in model_options:
        try:
            logger.info(f"Trying model: {model_name}")
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForSequenceClassification.from_pretrained(
                model_name, 
                num_labels=2,
                problem_type="single_label_classification"
            )
            
            # Add padding token if missing
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
                model.config.pad_token_id = model.config.eos_token_id
            
            logger.info(f"Successfully loaded: {model_name}")
            break
            
        except Exception as e:
            logger.warning(f"Failed to load {model_name}: {e}")
            continue
    
    if model is None:
        raise RuntimeError("Could not load any suitable model")
    
    return tokenizer, model, model_name

def compute_metrics(eval_pred):
    """Compute metrics for evaluation"""
    predictions, labels = eval_pred
    predictions = np.argmax(predictions, axis=1)
    
    accuracy = accuracy_score(labels, predictions)
    
    return {
        'accuracy': accuracy,
    }

class TemperatureScaling:
    """
    Temperature scaling for model calibration
    """
    def __init__(self):
        self.temperature = 1.0
    
    def fit(self, logits, labels):
        """
        Fit temperature scaling on validation set
        """
        from scipy.optimize import minimize_scalar
        
        def temperature_loss(temperature):
            """Negative log likelihood loss for temperature scaling"""
            scaled_logits = torch.tensor(logits) / temperature
            log_probs = torch.nn.functional.log_softmax(scaled_logits, dim=1)
            nll = torch.nn.functional.nll_loss(log_probs, torch.tensor(labels))
            return nll.item()
        
        # Find optimal temperature
        result = minimize_scalar(temperature_loss, bounds=(0.1, 10.0), method='bounded')
        self.temperature = result.x
        
        logger.info(f"Optimal temperature: {self.temperature:.4f}")
        return self
    
    def predict_proba(self, logits):
        """Apply temperature scaling to logits"""
        scaled_logits = torch.tensor(logits) / self.temperature
        return torch.nn.functional.softmax(scaled_logits, dim=1)

class PlattScaling:
    """
    Platt scaling for binary classification calibration
    """
    def __init__(self):
        self.platt_lr = LogisticRegression()
    
    def fit(self, confidences, labels):
        """
        Fit Platt scaling on validation set
        confidences: max confidence scores from model
        labels: true binary labels
        """
        # Convert to log odds for logistic regression
        confidences = np.array(confidences).reshape(-1, 1)
        self.platt_lr.fit(confidences, labels)
        
        logger.info("Platt scaling calibration fitted")
        return self
    
    def predict_proba(self, confidences):
        """Apply Platt scaling to confidence scores"""
        confidences = np.array(confidences).reshape(-1, 1)
        return self.platt_lr.predict_proba(confidences)

def calibrate_model_confidence(model, tokenizer, cal_texts, cal_labels, device):
    """
    Calibrate model confidence using temperature scaling and Platt scaling
    """
    logger.info("Performing confidence calibration...")
    
    model.eval()
    all_logits = []
    all_confidences = []
    
    with torch.no_grad():
        for text in cal_texts:
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=128)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            outputs = model(**inputs)
            logits = outputs.logits.cpu().numpy()
            confidence = torch.nn.functional.softmax(outputs.logits, dim=-1).max().item()
            
            all_logits.append(logits[0])
            all_confidences.append(confidence)
    
    all_logits = np.array(all_logits)
    
    # Temperature scaling
    temp_scaler = TemperatureScaling()
    temp_scaler.fit(all_logits, cal_labels)
    
    # Platt scaling for confidence scores
    platt_scaler = PlattScaling()
    platt_scaler.fit(all_confidences, cal_labels)
    
    # Calculate Expected Calibration Error (ECE) before and after calibration
    def calculate_ece(confidences, predictions, labels, n_bins=10):
        """Calculate Expected Calibration Error"""
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        bin_lowers = bin_boundaries[:-1]
        bin_uppers = bin_boundaries[1:]
        
        ece = 0.0
        for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
            in_bin = (confidences > bin_lower) & (confidences <= bin_upper)
            prop_in_bin = in_bin.mean()
            
            if prop_in_bin > 0:
                accuracy_in_bin = (predictions[in_bin] == labels[in_bin]).mean()
                avg_confidence_in_bin = confidences[in_bin].mean()
                ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
        
        return ece
    
    # Calculate pre-calibration ECE
    predictions = np.argmax(all_logits, axis=1)
    pre_ece = calculate_ece(np.array(all_confidences), predictions, np.array(cal_labels))
    
    # Calculate post-calibration ECE with temperature scaling
    try:
        temp_probs = temp_scaler.predict_proba(all_logits)
        temp_confidences = temp_probs.max(axis=1)
        if hasattr(temp_confidences, 'numpy'):
            temp_confidences = temp_confidences.numpy()
        temp_predictions = temp_probs.argmax(axis=1)
        if hasattr(temp_predictions, 'numpy'):
            temp_predictions = temp_predictions.numpy()
        post_temp_ece = calculate_ece(temp_confidences, temp_predictions, np.array(cal_labels))
    except Exception as e:
        logger.warning(f"Post-calibration ECE calculation failed: {e}")
        post_temp_ece = pre_ece  # Fallback to pre-calibration ECE
    
    logger.info(f"Pre-calibration ECE: {pre_ece:.4f}")
    logger.info(f"Post-temperature-scaling ECE: {post_temp_ece:.4f}")
    
    calibration_info = {
        'temperature': temp_scaler.temperature,
        'pre_calibration_ece': float(pre_ece),
        'post_calibration_ece': float(post_temp_ece),
        'calibration_method': 'temperature_scaling'
    }
    
    return temp_scaler, platt_scaler, calibration_info

def main():
    """Main training function"""
    # Setup paths
    project_root = Path(__file__).parent.parent.parent
    data_path = project_root / "router" / "data" / "intents_bootstrap.csv"
    
    # Fallback to TSV if CSV doesn't exist
    if not data_path.exists():
        data_path = project_root / "router" / "data" / "intents_bootstrap.tsv"
    
    if not data_path.exists():
        data_path = project_root / "router" / "data" / "intents.tsv"
    
    if not data_path.exists():
        raise FileNotFoundError(f"No training data found. Expected: {data_path}")
    
    output_dir = project_root / "router" / "train" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Check for GPU/MPS
    if torch.backends.mps.is_available():
        device = torch.device("mps")
        logger.info("Using Apple MPS")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
        logger.info("Using CUDA")
    else:
        device = torch.device("cpu")
        logger.info("Using CPU")
    
    # Load data
    df, label_map = load_data(data_path)
    
    # Split data into train/validation/calibration
    train_texts, temp_texts, train_labels, temp_labels = train_test_split(
        df['text'].tolist(),
        df['label_id'].tolist(),
        test_size=0.4,  # 40% for val+cal
        random_state=42,
        stratify=df['label_id']
    )
    
    # Split temp into validation and calibration
    val_texts, cal_texts, val_labels, cal_labels = train_test_split(
        temp_texts,
        temp_labels,
        test_size=0.5,  # 50% of temp = 20% of total for calibration
        random_state=42,
        stratify=temp_labels
    )
    
    logger.info(f"Train set: {len(train_texts)} examples")
    logger.info(f"Val set: {len(val_texts)} examples")
    logger.info(f"Calibration set: {len(cal_texts)} examples")
    
    # Setup model and tokenizer
    tokenizer, model, model_name = setup_model_and_tokenizer()
    
    # Move model to device
    model.to(device)
    
    # Create datasets
    train_dataset = IntentDataset(train_texts, train_labels, tokenizer)
    val_dataset = IntentDataset(val_texts, val_labels, tokenizer)
    
    # Training arguments - optimized for small dataset and model size
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=10,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        warmup_steps=10,
        weight_decay=0.01,
        logging_dir=str(output_dir / "logs"),
        logging_steps=5,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        greater_is_better=True,
        save_total_limit=2,
        seed=42,
        fp16=False,  # Disable for MPS compatibility
        dataloader_pin_memory=False,  # Better for MPS
        report_to=None,  # Disable wandb/tensorboard
    )
    
    # Create trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=3)]
    )
    
    # Train the model
    logger.info("Starting training...")
    trainer.train()
    
    # Evaluate
    logger.info("Evaluating...")
    eval_results = trainer.evaluate()
    logger.info(f"Validation results: {eval_results}")
    
    # Perform confidence calibration
    temp_scaler, platt_scaler, calibration_info = calibrate_model_confidence(
        model, tokenizer, cal_texts, cal_labels, device
    )
    
    # Save the final model
    final_model_path = output_dir / "final_model"
    trainer.save_model(str(final_model_path))
    tokenizer.save_pretrained(str(final_model_path))
    
    # Test on some examples
    logger.info("\nTesting on sample inputs:")
    test_examples = [
        "Generate a summary report",
        "Close all trading positions", 
        "Write me a poem",
        "Restart the server",
        "Emergency stop all bots"
    ]
    
    model.eval()
    label_names = {v: k for k, v in label_map.items()}
    
    with torch.no_grad():
        for text in test_examples:
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=128)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            outputs = model(**inputs)
            raw_logits = outputs.logits
            raw_prediction = torch.nn.functional.softmax(raw_logits, dim=-1)
            predicted_class = torch.argmax(raw_prediction, dim=-1).item()
            raw_confidence = raw_prediction[0][predicted_class].item()
            
            # Apply temperature scaling for calibrated confidence
            calibrated_probs = temp_scaler.predict_proba(raw_logits.cpu().numpy())
            calibrated_confidence = calibrated_probs[0].max()
            
            predicted_label = label_names[predicted_class]
            logger.info(f"'{text}' → {predicted_label} (raw: {raw_confidence:.3f}, calibrated: {calibrated_confidence:.3f})")
    
    # Save calibration scalers
    import pickle
    calibration_path = output_dir / "calibration.pkl"
    with open(calibration_path, 'wb') as f:
        pickle.dump({
            'temperature_scaler': temp_scaler,
            'platt_scaler': platt_scaler,
            'calibration_info': calibration_info
        }, f)
    
    logger.info(f"Calibration scalers saved to: {calibration_path}")
    
    # Save metadata with unique training ID
    import uuid
    training_id = str(uuid.uuid4())[:8]
    
    metadata = {
        'training_id': training_id,
        'model_name': model_name,
        'num_labels': 2,
        'label_map': label_map,
        'vocab_size': len(tokenizer),
        'max_length': 128,
        'validation_accuracy': eval_results['eval_accuracy'],
        'calibration': calibration_info,
        'calibration_file': str(calibration_path.name),
        'trained_at': pd.Timestamp.now().isoformat()
    }
    
    import json
    with open(output_dir / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # M7.5: Generate training summary for API access
    timestamp_now = pd.Timestamp.now().isoformat()
    train_summary = {
        'training_id': training_id,
        'timestamp': timestamp_now,
        'status': 'completed',
        'version': '2.0',
        'model': {
            'name': model_name,
            'architecture': 'transformer_classification',
            'num_parameters': sum(p.numel() for p in model.parameters()),
            'vocab_size': len(tokenizer),
            'num_labels': 2
        },
        'dataset': {
            'total_samples': len(df),
            'train_samples': len(train_texts),
            'val_samples': len(val_texts),
            'cal_samples': len(cal_texts),
            'label_distribution': df['label'].value_counts().to_dict()
        },
        'training': {
            'epochs_completed': training_args.num_train_epochs,
            'batch_size': training_args.per_device_train_batch_size,
            'learning_rate': training_args.learning_rate,
            'early_stopping_patience': 3,
            'device_used': str(device),
            'training_duration_minutes': None  # Will be calculated if available
        },
        'performance': {
            'validation_accuracy': float(eval_results['eval_accuracy']),
            'validation_loss': float(eval_results.get('eval_loss', 0.0)),
            'precision': None,  # Will be populated by evaluation
            'recall': None,     # Will be populated by evaluation
            'f1_score': None,   # Will be populated by evaluation
            'calibration': {
                'temperature': float(calibration_info['temperature']),
                'pre_calibration_ece': float(calibration_info['pre_calibration_ece']),
                'post_calibration_ece': float(calibration_info['post_calibration_ece']),
                'method': calibration_info['calibration_method']
            }
        },
        'files': {
            'model_path': str(final_model_path),
            'metadata_path': str(output_dir / "metadata.json"),
            'calibration_path': str(calibration_path),
            'output_directory': str(output_dir)
        },
        'coreml_models': {
            'SmallIntent': {
                'target_path': str(project_root / "router" / "SmallIntent.mlmodel"),
                'created': False,
                'size_mb': None
            },
            'TinyIntent': {
                'target_path': str(project_root / "router" / "TinyIntent.mlmodel"), 
                'created': False,
                'size_mb': None
            }
        },
        'sample_predictions': []
    }
    
    # Add sample predictions to summary
    model.eval()
    label_names = {v: k for k, v in label_map.items()}
    
    with torch.no_grad():
        for text in test_examples:
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=128)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            outputs = model(**inputs)
            raw_logits = outputs.logits
            raw_prediction = torch.nn.functional.softmax(raw_logits, dim=-1)
            predicted_class = torch.argmax(raw_prediction, dim=-1).item()
            raw_confidence = raw_prediction[0][predicted_class].item()
            
            # Apply temperature scaling for calibrated confidence
            calibrated_probs = temp_scaler.predict_proba(raw_logits.cpu().numpy())
            calibrated_confidence = calibrated_probs[0].max()
            predicted_label = label_names[predicted_class]
            
            train_summary['sample_predictions'].append({
                'text': text,
                'predicted_label': predicted_label,
                'raw_confidence': float(raw_confidence),
                'calibrated_confidence': float(calibrated_confidence)
            })
    
    # M7.5: Save training summary for API endpoint
    train_summary_path = project_root / "router" / "train_summary.json"
    with open(train_summary_path, 'w') as f:
        json.dump(train_summary, f, indent=2)
    
    logger.info(f"Training summary saved to: {train_summary_path}")
    
    logger.info(f"\nTraining complete!")
    logger.info(f"Model saved to: {final_model_path}")
    logger.info(f"Validation accuracy: {eval_results['eval_accuracy']:.4f}")
    logger.info(f"Temperature scaling parameter: {calibration_info['temperature']:.4f}")
    logger.info(f"Pre-calibration ECE: {calibration_info['pre_calibration_ece']:.4f}")
    logger.info(f"Post-calibration ECE: {calibration_info['post_calibration_ece']:.4f}")
    
    return final_model_path, metadata

if __name__ == "__main__":
    main()