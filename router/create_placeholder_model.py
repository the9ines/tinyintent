#!/usr/bin/env python3
"""
Create a minimal Core ML model placeholder for testing M2
This creates a basic text classifier that can be loaded by the Swift runtime
"""

import coremltools as ct
import numpy as np
from coremltools.models import MLModel
import coremltools.proto.Model_pb2 as Model_pb2

def create_placeholder_model():
    """Create a minimal Core ML text classifier"""
    
    # Create a simple lookup table for demo purposes
    # In practice, this would be a proper DistilBERT model
    
    # Define the labels
    labels = ["send_claude", "plan_then_claude", "local_only"]
    
    # Create model spec
    spec = Model_pb2.Model()
    spec.specificationVersion = 5
    
    # Set description
    spec.description.input.add().name = "text"
    spec.description.input[0].type.stringType.CopyFrom(Model_pb2.StringFeatureType())
    
    spec.description.output.add().name = "intent"
    spec.description.output[0].type.stringType.CopyFrom(Model_pb2.StringFeatureType())
    
    # Create a pipeline classifier
    pipeline = spec.pipelineClassifier
    
    # Add a simple string classifier stage
    stage = pipeline.pipeline.add()
    stage.nonMaximumSuppression.CopyFrom(Model_pb2.NonMaximumSuppressionLayerParams())
    
    # Set class labels
    pipeline.stringClassLabels.vector.extend(labels)
    
    # Create the model
    model = MLModel(spec)
    
    # Set metadata
    model.short_description = "TinyIntent placeholder classifier"
    model.author = "TinyIntent M2 Pipeline"
    model.version = "1.0.0"
    
    return model

def main():
    print("Creating placeholder Core ML model...")
    
    try:
        model = create_placeholder_model()
        output_path = "/Users/oberfelder/projects/smallintent/router/TinyIntent.mlmodel"
        model.save(output_path)
        print(f"Placeholder model saved to: {output_path}")
        
        # Check file size
        import os
        size = os.path.getsize(output_path)
        print(f"Model size: {size} bytes ({size/(1024*1024):.2f} MB)")
        
    except Exception as e:
        print(f"Error creating placeholder model: {e}")
        print("This is expected - Core ML model creation requires proper implementation")
        print("For M2 testing, we'll create a simple file placeholder")
        
        # Create a simple file placeholder for testing (uses .mlmodel format)
        output_path = "/Users/oberfelder/projects/smallintent/router/TinyIntent.mlmodel"
        with open(output_path, 'w') as f:
            f.write("# Placeholder Core ML model for M2 testing\n")
        print(f"Created file placeholder at: {output_path}")

if __name__ == "__main__":
    main()