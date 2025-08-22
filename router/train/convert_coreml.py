#!/usr/bin/env python3
"""
TinyIntent Router Core ML Conversion
Converts ONNX model to Core ML format with quantization
"""

import os
import json
import numpy as np
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def convert_onnx_to_coreml(onnx_path, output_path, quantize=True):
    """Convert ONNX model to Core ML format"""
    
    try:
        import coremltools as ct
        from coremltools.models.neural_network import quantization_utils
        import onnx
    except ImportError:
        raise ImportError("coremltools and onnx are required. Install with: pip install coremltools onnx")
    
    logger.info(f"Loading ONNX model: {onnx_path}")
    
    # Load ONNX model first
    try:
        onnx_model = onnx.load(str(onnx_path))
        logger.info("ONNX model loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load ONNX model: {e}")
        raise
    
    # Convert ONNX to Core ML
    conversion_strategies = [
        # Strategy 1: Modern approach with explicit ONNX conversion
        {
            "name": "Modern ONNX conversion",
            "func": lambda: ct.converters.onnx.convert(
                model=onnx_model,
                minimum_deployment_target=ct.target.macOS12,
                compute_precision=ct.precision.FLOAT16 if quantize else ct.precision.FLOAT32
            )
        },
        # Strategy 2: Legacy approach
        {
            "name": "Legacy ONNX conversion",
            "func": lambda: ct.converters.onnx.convert(
                model=onnx_model,
                minimum_deployment_target=ct.target.macOS11
            )
        },
        # Strategy 3: Direct path conversion
        {
            "name": "Direct path conversion",
            "func": lambda: ct.converters.onnx.convert(
                model=str(onnx_path)
            )
        },
        # Strategy 4: Minimal conversion
        {
            "name": "Minimal conversion",
            "func": lambda: ct.convert(onnx_model)
        }
    ]
    
    coreml_model = None
    for strategy in conversion_strategies:
        try:
            logger.info(f"Trying {strategy['name']}...")
            coreml_model = strategy['func']()
            logger.info(f"{strategy['name']} successful")
            break
        except Exception as e:
            logger.error(f"{strategy['name']} failed: {e}")
            continue
    
    if coreml_model is None:
        raise RuntimeError("All conversion strategies failed")
    
    # Add metadata
    coreml_model.short_description = "TinyIntent Router - Intent Classifier"
    coreml_model.input_description["input_ids"] = "Tokenized input text (sequence of token IDs)"
    coreml_model.input_description["attention_mask"] = "Attention mask for input tokens"
    coreml_model.output_description["logits"] = "Classification logits (gen=0, act=1)"
    
    # Additional quantization if requested and not already applied
    if quantize:
        try:
            logger.info("Applying additional quantization...")
            
            # Quantize weights to 8-bit
            quantized_model = quantization_utils.quantize_weights(
                coreml_model, 
                nbits=8
            )
            coreml_model = quantized_model
            logger.info("8-bit quantization applied")
            
        except Exception as e:
            logger.warning(f"Additional quantization failed: {e}")
    
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
            # Try more aggressive quantization for oversized models
            if not quantize:
                logger.info("Trying with quantization enabled...")
                return convert_onnx_to_coreml(onnx_path, output_path, quantize=True)
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

def create_optimized_model(onnx_path, output_path):
    """Create an optimized Core ML model with multiple attempts"""
    
    quantization_strategies = [
        {"quantize": True, "precision": "FLOAT16", "nbits": 8},
        {"quantize": True, "precision": "FLOAT16", "nbits": 4},
        {"quantize": False, "precision": "FLOAT16", "nbits": None},
        {"quantize": False, "precision": "FLOAT32", "nbits": None},
    ]
    
    for i, strategy in enumerate(quantization_strategies):
        try:
            logger.info(f"Trying conversion strategy {i+1}: {strategy}")
            
            model, size_mb = convert_onnx_to_coreml(
                onnx_path, 
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
    
    # Input paths
    onnx_path = project_root / "router" / "SmallIntent.onnx"
    tokenizer_path = project_root / "router" / "train" / "output" / "final_model"
    
    # Try alternative output directories if default doesn't exist
    if not tokenizer_path.exists():
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
    
    if not onnx_path.exists():
        raise FileNotFoundError(f"ONNX model not found: {onnx_path}")
    
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
        
        model, size_mb = create_optimized_model(onnx_path, small_model_path)
        test_coreml_model(small_model_path, tokenizer_path)
        
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
        metadata_path = project_root / "router" / "train" / "output" / "metadata.json"
        if not metadata_path.exists():
            # Try alternative locations
            for output_dir in ["train_output", "train_enhanced_output", "train_fixed_output", "train_improved_output"]:
                alt_metadata = project_root / "router" / output_dir / "metadata.json"
                if alt_metadata.exists():
                    metadata_path = alt_metadata
                    break
        
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
        else:
            metadata = {}
        
        # Add model information
        metadata['coreml_models'] = {}
        for model_name, model_path, model_size in created_models:
            metadata['coreml_models'][model_name.lower()] = {
                'path': str(model_path),
                'size_mb': model_size,
                'meets_size_constraint': (50 <= model_size <= 100) if model_name == 'SmallIntent' else model_size <= 5,
                'target_platform': 'macOS' if model_name == 'SmallIntent' else 'iOS'
            }
        
        # Legacy fields for backward compatibility
        metadata['coreml_path'] = str(small_model_path)
        metadata['coreml_size_mb'] = created_models[0][2]  # SmallIntent size
        metadata['meets_size_constraint'] = 50 <= created_models[0][2] <= 100  # SmallIntent size range
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"✅ Metadata updated: {metadata_path}")
        logger.info("✅ CoreML model creation completed successfully!")
        
        # Print summary
        logger.info("\nModel Summary:")
        for model_name, model_path, model_size in created_models:
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