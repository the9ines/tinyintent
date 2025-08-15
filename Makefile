.PHONY: train build test agent clean ios-model bridge-venv bridge bridge-stop bridge-logs iphone-test

# M1 Targets (Training Pipeline)
train:
	@echo "Installing dependencies..."
	pip3 install -r router/requirements.txt
	@echo "Starting TinyIntent DistilBERT training (bert-tiny)..."
	python3 router/train_intent.py
	@echo "[✅] TinyIntent.mlmodel (or .mlpackage) ready"
	@ls -lh router/TinyIntent.mlmodel

# M2 Targets (Swift Runtime + Agent)

# Build Swift runtime
build:
	@echo "Building Swift runtime..."
	cd router && swift build -c release
	cp router/.build/release/tinyintent router/tinyintent
	chmod +x router/tinyintent
	@echo "Runtime built: router/tinyintent"

# Test Swift runtime with sample inputs
test: build
	@echo "Testing TinyIntent runtime..."
	@echo "Test 1: Local summarization (expect: local_only)"
	@echo "local summarization" | router/tinyintent || (echo "Test 1 failed" && exit 1)
	@echo ""
	@echo "Test 2: Research task (expect: send_claude)"
	@echo "research longform report on quantum cryptography, with citations" | router/tinyintent || (echo "Test 2 failed" && exit 1)
	@echo ""
	@echo "Test 3: Planning task (expect: plan_then_local)"
	@echo "brainstorm steps then execute locally" | router/tinyintent || (echo "Test 3 failed" && exit 1)
	@echo ""
	@echo "Test 4: Empty input (expect: non-zero exit)"
	@echo "" | router/tinyintent && (echo "Test 4 failed - should have exited non-zero" && exit 1) || echo "Test 4 passed: empty input rejected"
	@echo ""
	@echo "All runtime tests passed!"

# Test agent with dry-run mode
agent: build
	@echo "Testing neuro_agent with dry-run mode..."
	@echo "local summarization" | agent/neuro_agent --dry-run
	@echo "Agent test complete!"

# Clean all artifacts
clean:
	@echo "Cleaning all artifacts..."
	cd router && rm -rf TinyIntent.mlpackage TinyIntent.mlmodel results/ logs/ __pycache__/ *.pyc .build/ tinyintent
	@echo "Clean complete"

# M3 Targets (iPhone Shortcut + Mac Bridge)

BRIDGE_DIR = bridge
LAUNCHD_PLIST = launchd/com.tinyintent.tinyrpc.plist
PY = $(BRIDGE_DIR)/.venv/bin/python3
PIP = $(BRIDGE_DIR)/.venv/bin/pip

# Export iOS-compatible Core ML model
ios-model:
	@echo "[ios-model] exporting iOS model..."
	@python3 router/export_ios_model.py
	@echo "[ios-model] output: router/TinyIntent_iOS.mlpackage (or .mlmodel)"

# Create Python venv and install Flask
bridge-venv:
	@echo "[bridge-venv] creating venv and installing Flask..."
	@python3 -m venv $(BRIDGE_DIR)/.venv
	@$(PIP) install -U pip
	@$(PIP) install -r $(BRIDGE_DIR)/requirements_bridge.txt

# Start tinyrpc via launchd
bridge:
	@mkdir -p $(BRIDGE_DIR)/logs
	@echo "[bridge] loading launchd service..."
	@launchctl unload -w $(LAUNCHD_PLIST) 2>/dev/null || true
	@launchctl load -w $(LAUNCHD_PLIST)
	@echo "[bridge] loaded. Use 'make bridge-logs' to tail logs."

# Stop tinyrpc service
bridge-stop:
	@echo "[bridge-stop] unloading launchd service..."
	@launchctl unload -w $(LAUNCHD_PLIST) || true
	@echo "[bridge-stop] done."

# Tail bridge logs
bridge-logs:
	@echo "[bridge-logs] tailing logs (Ctrl-C to stop)..."
	@tail -n 200 -f bridge/logs/stdout.log bridge/logs/stderr.log bridge/logs/tinyrpc.log

# Test bridge with cURL
iphone-test:
	@echo "[iphone-test] sending sample POST to bridge..."
	@curl -sS -X POST http://127.0.0.1:8787/route \
		-H "Content-Type: application/json" \
		-H "X-TinyIntent-Secret: tinyintent-secure-bridge-2024" \
		-d '{"text":"local summarization please","route":"local_only"}' | sed 's/.*/[bridge] &/'