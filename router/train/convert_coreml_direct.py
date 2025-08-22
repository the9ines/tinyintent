#!/usr/bin/env python3
"""
TinyIntent Router Direct PyTorch to Core ML Conversion
Converts PyTorch model directly to Core ML, bypassing ONNX
"""

import os
import json
import numpy as np
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def convert_pytorch_to_coreml(model_path, output_path, quantize=True):
    """Convert PyTorch model directly to Core ML format"""
    
    try:
        import coremltools as ct
    except ImportError:
        raise ImportError("coremltools is required. Install with: pip install coremltools")
    
    logger.info(f"Loading PyTorch model from: {model_path}")
    
    # Load the fine-tuned model and tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSequenceClassification.from_pretrained(model_path)
    
    # Set model to evaluation mode
    model.eval()
    
    # Create example input for tracing
    dummy_text = "Generate a summary report"
    dummy_input = tokenizer(
        dummy_text,
        truncation=True,
        padding='max_length',
        max_length=128,
        return_tensors='pt'
    )
    
    input_ids = dummy_input['input_ids']
    attention_mask = dummy_input['attention_mask']
    
    logger.info(f"Input shape: {input_ids.shape}")
    logger.info(f"Attention mask shape: {attention_mask.shape}")
    
    # Create a wrapper model that returns only logits (not dict)
    class ModelWrapper(torch.nn.Module):
        def __init__(self, model):
            super().__init__()
            self.model = model
        
        def forward(self, input_ids, attention_mask):
            outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
            return outputs.logits  # Return only logits, not the dict
    
    wrapper_model = ModelWrapper(model)
    wrapper_model.eval()
    
    # Create traced model
    logger.info("Creating traced PyTorch model...")
    with torch.no_grad():
        traced_model = torch.jit.trace(wrapper_model, (input_ids, attention_mask), strict=False)
    
    logger.info("Converting traced model to Core ML...")
    
    # Convert to Core ML
    try:
        if quantize:
            # Use newer format for quantization support
            coreml_model = ct.convert(
                traced_model,
                inputs=[
                    ct.TensorType(name="input_ids", shape=(1, 128), dtype=np.int32),
                    ct.TensorType(name="attention_mask", shape=(1, 128), dtype=np.int32)
                ],
                minimum_deployment_target=ct.target.macOS13,
                compute_precision=ct.precision.FLOAT16
            )
        else:
            # Use legacy format for broader compatibility
            coreml_model = ct.convert(
                traced_model,
                inputs=[
                    ct.TensorType(name="input_ids", shape=(1, 128), dtype=np.int32),
                    ct.TensorType(name="attention_mask", shape=(1, 128), dtype=np.int32)
                ],
                minimum_deployment_target=ct.target.macOS11
            )
        
        logger.info("PyTorch to Core ML conversion successful")
        
    except Exception as e:
        logger.error(f"Direct conversion failed: {e}")
        logger.info("Trying alternative conversion approach...")
        
        # Fallback: try with minimal parameters
        try:
            coreml_model = ct.convert(
                traced_model,
                minimum_deployment_target=ct.target.macOS11
            )
            logger.info("Alternative conversion successful")
        except Exception as e2:
            logger.error(f"Alternative conversion also failed: {e2}")
            raise
    
    # Add metadata
    coreml_model.short_description = "TinyIntent Router - Intent Classifier"
    try:
        coreml_model.input_description["input_ids"] = "Tokenized input text (sequence of token IDs)"
        coreml_model.input_description["attention_mask"] = "Attention mask for input tokens"
        coreml_model.output_description["var_50"] = "Classification logits (gen=0, act=1)"  # Output name may vary
    except Exception as e:
        logger.warning(f"Could not set input/output descriptions: {e}")
    
    # Save the model
    logger.info(f"Saving Core ML model: {output_path}")
    coreml_model.save(str(output_path))
    
    # Check model size
    if output_path.exists():
        # Core ML models are directories, get total size
        total_size = sum(f.stat().st_size for f in output_path.rglob('*') if f.is_file())
        size_mb = total_size / (1024 * 1024)
        logger.info(f"Core ML model size: {size_mb:.2f} MB")
        
        # Validate target size range (50-100 MB for higher-capacity model)
        if size_mb < 50:
            logger.warning(f"Model size ({size_mb:.2f} MB) below minimum target (50 MB)")
        elif size_mb > 100:
            logger.warning(f"Model size ({size_mb:.2f} MB) exceeds maximum target (100 MB)")
        else:
            logger.info(f"✅ Model size: {size_mb:.2f} MB (target: 70-85 MB)")
    
    return coreml_model, size_mb

def test_coreml_model(model_path, tokenizer_path):
    """Test the Core ML model"""
    try:
        import coremltools as ct
        from transformers import AutoTokenizer
    except ImportError as e:
        logger.warning(f"Cannot test Core ML model: {e}")
        return
    
    logger.info("Testing Core ML model...")
    
    # Load the model
    model = ct.models.MLModel(str(model_path))
    
    # Load tokenizer for preprocessing
    try:
        tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
    except Exception as e:
        logger.warning(f"Could not load tokenizer for testing: {e}")
        return
    
    # Test examples
    test_examples = [
        "Generate a summary report",
        "Close all trading positions", 
        "Write me a poem",
        "Restart the server"
    ]
    
    for text in test_examples:
        try:
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
            
            # Extract logits (the key might vary)
            logits_key = list(prediction.keys())[0]  # Get first output
            logits = prediction[logits_key]
            
            # Get prediction
            if len(logits.shape) > 1:
                predicted_class = np.argmax(logits[0])
                confidence = np.exp(logits[0]) / np.sum(np.exp(logits[0]))  # softmax
                conf_score = confidence[predicted_class]
            else:
                predicted_class = np.argmax(logits)
                conf_score = 0.0
            
            label = "gen" if predicted_class == 0 else "act"
            logger.info(f"'{text}' → {label} (confidence: {conf_score:.3f})")
            
        except Exception as e:
            logger.error(f"Failed to test '{text}': {e}")

def create_optimized_model(model_path, output_path):
    """Create an optimized Core ML model with multiple attempts"""
    
    strategies = [
        {"quantize": True, "desc": "FLOAT16 quantized"},
        {"quantize": False, "desc": "FLOAT32 unquantized"},
    ]
    
    for i, strategy in enumerate(strategies):
        try:
            logger.info(f"Trying strategy {i+1}: {strategy['desc']}")
            
            model, size_mb = convert_pytorch_to_coreml(
                model_path, 
                output_path, 
                quantize=strategy["quantize"]
            )
            
            if 50 <= size_mb <= 100:
                logger.info(f"✅ Success! Model size: {size_mb:.2f} MB (within target range)")
                return model, size_mb
            else:
                logger.warning(f"Model size {size_mb:.2f} MB outside target range (50-100MB), trying next strategy...")
                # Remove the oversized model
                if output_path.exists():
                    import shutil
                    shutil.rmtree(output_path)
                    
        except Exception as e:
            logger.error(f"Strategy {i+1} failed: {e}")
            continue
    
    raise RuntimeError("All conversion strategies failed to create a valid model")

def main():
    """Main conversion function"""
    project_root = Path(__file__).parent.parent.parent
    
    # Input model path
    model_path = project_root / "router" / "train" / "output" / "final_model"
    
    # Try alternative output directories if default doesn't exist
    if not model_path.exists():
        output_dirs = [
            "train_output",
            "train_enhanced_output", 
            "train_fixed_output",
            "train_improved_output"
        ]
        
        for output_dir in output_dirs:
            alt_path = project_root / "router" / output_dir / "final_model"
            if alt_path.exists():
                model_path = alt_path
                break
    
    if not model_path.exists():
        raise FileNotFoundError(f"PyTorch model not found: {model_path}")
    
    # Output paths for both models
    small_model_path = project_root / "router" / "SmallIntent.mlmodel"
    tiny_model_path = project_root / "router" / "TinyIntent.mlmodel"
    
    created_models = []
    
    try:
        # Create SmallIntent.mlmodel (standard model)
        logger.info("Creating SmallIntent.mlmodel...")
        if small_model_path.exists():
            import shutil
            shutil.rmtree(small_model_path)
        
        model, size_mb = create_optimized_model(model_path, small_model_path)
        test_coreml_model(small_model_path, model_path)
        
        logger.info(f"✅ SmallIntent.mlmodel created: {size_mb:.2f} MB")
        created_models.append(("SmallIntent", small_model_path, size_mb))
        
        # Create TinyIntent.mlmodel (more aggressive quantization for mobile)
        logger.info("Creating TinyIntent.mlmodel with aggressive quantization...")
        if tiny_model_path.exists():
            import shutil
            shutil.rmtree(tiny_model_path)
        
        # Create more aggressively quantized version for TinyIntent
        try:
            import coremltools as ct
            from coremltools.models.neural_network import quantization_utils
            
            # Load the base model
            base_model = ct.models.MLModel(str(small_model_path))
            
            # Apply more aggressive quantization for TinyIntent
            tiny_model = quantization_utils.quantize_weights(base_model, nbits=4)
            
            # Update metadata for mobile deployment
            tiny_model.short_description = "TinyIntent Router - Ultra-Compact Intent Classifier"
            tiny_model.save(str(tiny_model_path))
            
            # Check size
            tiny_size_mb = sum(f.stat().st_size for f in tiny_model_path.rglob('*') if f.is_file()) / (1024 * 1024)
            
            if tiny_size_mb <= 5:  # 5MB target for TinyIntent
                logger.info(f"✅ TinyIntent.mlmodel created: {tiny_size_mb:.2f} MB")
                created_models.append(("TinyIntent", tiny_model_path, tiny_size_mb))
            else:
                logger.warning(f"TinyIntent model too large: {tiny_size_mb:.2f} MB > 5MB target")
                # Keep it anyway but mark as oversized
                created_models.append(("TinyIntent", tiny_model_path, tiny_size_mb))
                
        except Exception as e:
            logger.warning(f"Failed to create TinyIntent.mlmodel: {e}")
            # Create a copy of SmallIntent as fallback
            import shutil
            shutil.copytree(small_model_path, tiny_model_path)
            created_models.append(("TinyIntent", tiny_model_path, size_mb))
        
        # Update metadata with both models
        metadata_path = model_path.parent / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
        else:
            metadata = {}
        
        # Add model information with versioning
        import datetime
        timestamp = datetime.datetime.utcnow().isoformat() + 'Z'
        
        metadata['coreml_models'] = {
            'created_at': timestamp,
            'training_id': metadata.get('training_id', 'unknown'),
            'models': {}
        }
        
        for model_name, model_path_obj, model_size in created_models:
            metadata['coreml_models']['models'][model_name.lower()] = {
                'path': str(model_path_obj),
                'size_mb': model_size,
                'meets_size_constraint': (50 <= model_size <= 100) if model_name == 'SmallIntent' else model_size <= 5,
                'target_platform': 'macOS' if model_name == 'SmallIntent' else 'iOS',
                'created_at': timestamp,
                'version': f"{timestamp.split('T')[0]}-{model_name.lower()}"
            }
        
        # Legacy fields for backward compatibility
        metadata['coreml_path'] = str(small_model_path)
        metadata['coreml_size_mb'] = created_models[0][2]  # SmallIntent size
        metadata['meets_size_constraint'] = 50 <= created_models[0][2] <= 100  # SmallIntent size range
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"✅ Metadata updated: {metadata_path}")
        
        # Update train_summary.json with CoreML model information
        train_summary_path = project_root / "train_summary.json"
        if train_summary_path.exists():
            try:
                with open(train_summary_path, 'r') as f:
                    train_summary = json.load(f)
                
                # Update CoreML model status
                if 'coreml_models' in train_summary:
                    for model_name, model_path_obj, model_size in created_models:
                        model_key = model_name
                        if model_key in train_summary['coreml_models']:
                            train_summary['coreml_models'][model_key]['created'] = True
                            train_summary['coreml_models'][model_key]['size_mb'] = model_size
                            train_summary['coreml_models'][model_key]['version'] = f"{timestamp.split('T')[0]}-{model_name.lower()}"
                            train_summary['coreml_models'][model_key]['created_at'] = timestamp
                
                # Save updated train summary
                with open(train_summary_path, 'w') as f:
                    json.dump(train_summary, f, indent=2)
                
                logger.info(f"✅ Updated training summary: {train_summary_path}")
                
            except Exception as e:
                logger.warning(f"Failed to update training summary: {e}")
        
        logger.info("✅ CoreML model creation completed successfully!")
        
        # Print summary
        logger.info("\nModel Summary:")
        for model_name, model_path_obj, model_size in created_models:
            if model_name == 'SmallIntent':
                target_desc = "50-100MB"
                status = "✅" if 50 <= model_size <= 100 else "⚠️"
            else:
                target_desc = "≤5MB"
                status = "✅" if model_size <= 5 else "⚠️"
            logger.info(f"  {status} {model_name}: {model_size:.2f} MB (target: {target_desc})")
        
        return created_models
        
    except Exception as e:
        logger.error(f"Core ML conversion failed: {e}")
        raise

if __name__ == "__main__":
    main()