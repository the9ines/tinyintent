.PHONY: train clean

# Train the TinyIntent model
train:
	@echo "Installing dependencies..."
	pip3 install -r requirements.txt
	@echo "Starting TinyIntent training..."
	python3 train_intent_simple.py
	@echo "Training complete!"

# Clean artifacts
clean:
	@echo "Cleaning TinyIntent artifacts..."
	rm -rf TinyIntent.mlpackage
	rm -rf TinyIntent.mlmodel
	rm -rf results/
	rm -rf logs/
	rm -rf __pycache__/
	rm -f *.pyc
	@echo "Clean complete"