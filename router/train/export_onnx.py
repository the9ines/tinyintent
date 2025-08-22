#!/usr/bin/env python3
"""
TinyIntent Router ONNX Export
Converts fine-tuned PyTorch model to ONNX format
"""

import os
import json
import torch
import torch.onnx
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def export_to_onnx(model_path, output_path, max_length=128):
    """Export PyTorch model to ONNX format"""
    
    logger.info(f"Loading model from: {model_path}")
    
    # Load the fine-tuned model and tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSequenceClassification.from_pretrained(model_path)
    
    # Set model to evaluation mode
    model.eval()
    
    # Create dummy input for tracing
    dummy_text = "Generate a summary report"
    dummy_input = tokenizer(
        dummy_text,
        truncation=True,
        padding='max_length',
        max_length=max_length,
        return_tensors='pt'
    )
    
    input_ids = dummy_input['input_ids']
    attention_mask = dummy_input['attention_mask']
    
    logger.info(f"Input shape: {input_ids.shape}")
    logger.info(f"Attention mask shape: {attention_mask.shape}")
    
    # Define input and output names
    input_names = ['input_ids', 'attention_mask']
    output_names = ['logits']
    
    # Dynamic axes for variable sequence length
    dynamic_axes = {
        'input_ids': {0: 'batch_size', 1: 'sequence_length'},
        'attention_mask': {0: 'batch_size', 1: 'sequence_length'},
        'logits': {0: 'batch_size'}
    }
    
    # Export to ONNX
    logger.info(f"Exporting to ONNX: {output_path}")
    
    with torch.no_grad():
        torch.onnx.export(
            model,
            (input_ids, attention_mask),
            str(output_path),
            export_params=True,
            opset_version=11,
            do_constant_folding=True,
            input_names=input_names,
            output_names=output_names,
            dynamic_axes=dynamic_axes,
            verbose=False
        )
    
    logger.info("ONNX export completed successfully")
    
    # Verify the exported model
    try:
        import onnx
        onnx_model = onnx.load(str(output_path))
        onnx.checker.check_model(onnx_model)
        logger.info("ONNX model verification passed")
        
        # Get model size
        model_size_mb = output_path.stat().st_size / (1024 * 1024)
        logger.info(f"ONNX model size: {model_size_mb:.2f} MB")
        
    except ImportError:
        logger.warning("ONNX not available for verification")
    except Exception as e:
        logger.error(f"ONNX verification failed: {e}")
    
    return output_path

def test_onnx_model(onnx_path, model_path):
    """Test the ONNX model with sample inputs"""
    try:
        import onnxruntime as ort
    except ImportError:
        logger.warning("ONNXRuntime not available for testing")
        return
    
    logger.info("Testing ONNX model...")
    
    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    
    # Create ONNX runtime session
    ort_session = ort.InferenceSession(str(onnx_path))
    
    # Test examples
    test_examples = [
        "Generate a summary report",
        "Close all trading positions", 
        "Write me a poem",
        "Restart the server"
    ]
    
    for text in test_examples:
        # Tokenize input
        inputs = tokenizer(
            text,
            truncation=True,
            padding='max_length',
            max_length=128,
            return_tensors='np'
        )
        
        # Run inference
        ort_inputs = {
            'input_ids': inputs['input_ids'],
            'attention_mask': inputs['attention_mask']
        }
        
        ort_outputs = ort_session.run(None, ort_inputs)
        logits = ort_outputs[0]
        
        # Get prediction
        predicted_class = logits.argmax(axis=1)[0]
        confidence = torch.nn.functional.softmax(torch.from_numpy(logits), dim=-1)[0]
        
        label = "gen" if predicted_class == 0 else "act"
        conf_score = confidence[predicted_class].item()
        
        logger.info(f"'{text}' → {label} (confidence: {conf_score:.3f})")

def main():
    """Main export function"""
    project_root = Path(__file__).parent.parent.parent
    
    # Input model path
    model_path = project_root / "router" / "train" / "output" / "final_model"
    
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    
    # Output ONNX path
    onnx_output_path = project_root / "router" / "SmallIntent.onnx"
    
    # Export to ONNX
    export_to_onnx(model_path, onnx_output_path)
    
    # Test the exported model
    test_onnx_model(onnx_output_path, model_path)
    
    # Load and save metadata
    metadata_path = model_path.parent / "metadata.json"
    if metadata_path.exists():
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        # Add ONNX info
        metadata['onnx_path'] = str(onnx_output_path)
        metadata['onnx_size_mb'] = onnx_output_path.stat().st_size / (1024 * 1024)
        
        # Save updated metadata
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    logger.info(f"ONNX model exported to: {onnx_output_path}")
    return onnx_output_path

if __name__ == "__main__":
    main()