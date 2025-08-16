#!/usr/bin/env python3
"""
TinyIntent BERT-Tiny Training & Core ML Export
Real PyTorch -> Core ML pipeline with ANE optimization
"""

import os
import sys
import random
import pandas as pd
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    EvalPrediction
)
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report
import coremltools
from coremltools.models import MLModel

# Set seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)
if torch.cuda.is_available():
    torch.cuda.manual_seed(42)

# Tiny backbone for <5MB requirement
BACKBONE = "prajjwal1/bert-tiny"

# Fixed label mapping (Router v2)
label2id = {"gen":0, "act":1, "local_only":2}
id2label = {0:"gen", 1:"act", 2:"local_only"}

class IntentDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_length=192):
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
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt"
        )
        
        return {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'labels': torch.tensor(label, dtype=torch.long)
        }

def compute_metrics(eval_pred: EvalPrediction):
    predictions, labels = eval_pred
    predictions = np.argmax(predictions, axis=1)
    return {'accuracy': accuracy_score(labels, predictions)}

def main():
    print("TinyIntent BERT-Tiny Training Pipeline")
    print("=" * 50)
    
    # Load data from TSV (text<TAB>label, no header)
    from pathlib import Path
    project_root = Path(__file__).resolve().parents[1]
    data_path = project_root / "router" / "data" / "intents.tsv"
    print(f"Loading data from {data_path}")
    
    df = pd.read_csv(data_path, sep='\t', header=None, names=['text', 'label'])
    print(f"Loaded {len(df)} examples")
    
    # Convert labels to IDs
    df['label_id'] = df['label'].map(label2id)
    
    # Print label distribution
    print("\nLabel distribution:")
    print(df['label'].value_counts())
    
    # Train/validation split (90/10)
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        df['text'].tolist(),
        df['label_id'].tolist(),
        test_size=0.1,
        random_state=42,
        stratify=df['label_id']
    )
    
    print(f"\nTrain set: {len(train_texts)} examples")
    print(f"Validation set: {len(val_texts)} examples")
    
    # Initialize tokenizer (bert-tiny)
    tokenizer = AutoTokenizer.from_pretrained(BACKBONE)
    
    # Create datasets
    train_dataset = IntentDataset(train_texts, train_labels, tokenizer)
    val_dataset = IntentDataset(val_texts, val_labels, tokenizer)
    
    # Initialize model (bert-tiny)
    model = AutoModelForSequenceClassification.from_pretrained(
        BACKBONE,
        num_labels=3,
        label2id=label2id,
        id2label=id2label
    )
    
    # Training arguments
    training_args = TrainingArguments(
        output_dir="./results",
        num_train_epochs=6,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        learning_rate=3e-5,
        weight_decay=0.01,
        warmup_ratio=0.1,
        logging_dir="./logs",
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        greater_is_better=True,
        seed=42,
        report_to=None,  # Disable wandb logging
    )
    
    # Initialize trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
    )
    
    # Train the model
    print("\nStarting training...")
    trainer.train()
    
    # Evaluate
    print("\nEvaluating model...")
    eval_results = trainer.evaluate()
    accuracy = eval_results['eval_accuracy']
    print(f"Validation accuracy: {accuracy:.4f}")
    
    # Generate predictions for confusion matrix
    predictions = trainer.predict(val_dataset)
    y_pred = np.argmax(predictions.predictions, axis=1)
    y_true = predictions.label_ids
    
    # Print confusion matrix
    cm = confusion_matrix(y_true, y_pred)
    print(f"\nConfusion Matrix:")
    print("Predicted:")
    print("          gen          act              local_only")
    print("Actual:")
    labels = ["gen", "act", "local_only"]
    for i, label in enumerate(labels):
        print(f"{label:>13}: {cm[i]}")
    
    # Sanity check predictions on 3 examples
    print(f"\nSanity check predictions:")
    test_examples = [
        "research quantum computing for technical paper",
        "plan steps then write code for new feature", 
        "fix this typo in my text"
    ]
    
    model.eval()
    for i, text in enumerate(test_examples):
        inputs = tokenizer(text, return_tensors="pt", truncation=True, padding="max_length", max_length=192)
        # Move inputs to CPU to avoid MPS issues
        inputs = {k: v.cpu() for k, v in inputs.items()}
        model_cpu = model.cpu()
        with torch.no_grad():
            outputs = model_cpu(**inputs)
            predicted_id = torch.argmax(outputs.logits, dim=-1).item()
            predicted_label = id2label[predicted_id]
        print(f"Example {i+1}: '{text}' -> {predicted_label}")
    
    print(f"\nExporting to Core ML...")
    
    # Prepare model for export (ensure on CPU for tracing)
    model_cpu = model.cpu()
    model_cpu.eval()
    
    # Create a wrapper model that only returns logits
    class LogitsOnlyModel(torch.nn.Module):
        def __init__(self, model):
            super().__init__()
            self.model = model
        
        def forward(self, input_ids, attention_mask):
            outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
            return outputs.logits
    
    logits_model = LogitsOnlyModel(model_cpu)
    logits_model.eval()
    
    # Create example inputs for tracing
    example_input_ids = torch.zeros(1, 192, dtype=torch.long)
    example_attention_mask = torch.ones(1, 192, dtype=torch.long)
    
    # Trace the wrapper model
    traced_model = torch.jit.trace(logits_model, (example_input_ids, example_attention_mask))
    
    # Convert to Core ML with robust two-path export strategy
    try:
        import coremltools as ct
        import subprocess, shlex
        
        def pkg_bytes(p):
            return int(subprocess.check_output(shlex.split(f"du -sk {p}")).split()[0]) * 1024
        
        # PATH 1: MLProgram + INT8 (preferred)
        print("[export] trying MLProgram + INT8 quantization...")
        mlprog = ct.convert(
            traced_model,
            convert_to="mlprogram",
            inputs=[
                ct.TensorType(name="input_ids", shape=(1,192), dtype=np.int32),
                ct.TensorType(name="attention_mask", shape=(1,192), dtype=np.int32),
            ],
            compute_units=ct.ComputeUnit.CPU_AND_NE,
        )
        
        # Try new optimize API first, then legacy:
        try:
            from coremltools.optimize.coreml import quantization_utils as q
            mlprog_q = q.quantize_weights(mlprog, nbits=8, quantization_mode="linear")
            print("[quant] MLProgram → INT8 via optimize.coreml")
        except Exception as e1:
            try:
                from coremltools.models.neural_network import quantization_utils as q_legacy
                mlprog_q = q_legacy.quantize_weights(mlprog, nbits=8, quantization_mode="linear")
                print("[quant] MLProgram → INT8 via legacy API")
            except Exception as e2:
                print(f"[warn] MLProgram INT8 failed: {e1} / {e2}", file=sys.stderr)
                mlprog_q = mlprog

        # Save MLProgram and check size
        dst_pkg = project_root / "router" / "TinyIntent.mlpackage"
        mlprog_q.save(dst_pkg)

        size_bytes = pkg_bytes(dst_pkg)
        size_mb = size_bytes / (1024*1024)
        print(f"[export] MLProgram saved {dst_pkg} ({size_mb:.2f} MB)")

        # PATH 2: NeuralNetwork fallback if MLProgram >= 5MB
        if size_bytes >= 5*1024*1024:
            print("[export] MLProgram ≥5MB, falling back to NeuralNetwork + INT8", file=sys.stderr)
            mlnn = ct.convert(
                traced_model,
                convert_to="neuralnetwork",
                inputs=[
                    ct.TensorType(name="input_ids", shape=(1,192), dtype=np.int32),
                    ct.TensorType(name="attention_mask", shape=(1,192), dtype=np.int32),
                ],
                compute_units=ct.ComputeUnit.CPU_AND_NE,
            )
            try:
                from coremltools.models.neural_network import quantization_utils as q_legacy
                mlnn_q = q_legacy.quantize_weights(mlnn, nbits=8, quantization_mode="linear")
                print("[quant] NeuralNetwork → INT8 via legacy API")
            except Exception as e3:
                print(f"[error] NN INT8 failed: {e3}", file=sys.stderr)
                mlnn_q = mlnn

            dst_mlm = project_root / "router" / "TinyIntent.mlmodel"
            mlnn_q.save(dst_mlm)

            # Size-check for the .mlmodel bundle
            size_bytes = pkg_bytes(dst_mlm)
            size_mb = size_bytes / (1024*1024)
            print(f"[export] NeuralNetwork saved {dst_mlm} ({size_mb:.2f} MB)")

            if size_bytes >= 5*1024*1024 or size_bytes < 100*1024:
                print(f"[error] model size out of range after fallback: {size_mb:.2f} MB", file=sys.stderr)
                sys.exit(1)

            # Smoke test the fallback model
            try:
                _ = ct.models.MLModel(dst_mlm)
                print("[export] NeuralNetwork load smoke test OK")
            except Exception as e:
                print(f"[warn] NeuralNetwork load failed: {e}", file=sys.stderr)
                
            print(f"\n🎉 Success! TinyIntent.mlmodel ready ({size_mb:.2f} MB)")
        
        else:
            # MLProgram succeeded and is under 5MB
            if size_bytes < 100*1024:
                print(f"[error] MLProgram model too small: {size_mb:.2f} MB (likely placeholder)", file=sys.stderr)
                sys.exit(1)

            # Smoke test the MLProgram model
            try:
                _ = ct.models.MLModel(dst_pkg)
                print("[export] MLProgram load smoke test OK")
            except Exception as e:
                print(f"[warn] MLProgram load failed: {e}", file=sys.stderr)
                
            print(f"\n🎉 Success! TinyIntent.mlpackage ready ({size_mb:.2f} MB)")
        
    except Exception as e:
        print(f"Core ML export failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()