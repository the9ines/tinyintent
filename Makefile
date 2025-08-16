SHELL := /bin/bash -eo pipefail

.PHONY: bootstrap
bootstrap:
	[ -d .venv ] || python3 -m venv .venv
	. .venv/bin/activate && pip install -U pip && pip install "Flask>=2.3,<3.1" "jsonschema>=4.18,<5" pyyaml
	mkdir -p bridge/logs data/episodes
	@echo "Bootstrap complete."

.PHONY: bridge-logs
bridge-logs:
	@tail -n 200 -f bridge/logs/stdout.log bridge/logs/stderr.log

.PHONY: doctor
doctor:
	python3 -c "import os, shutil, subprocess, yaml; roles = yaml.safe_load(open('models.yaml'))['roles']; print('roles:', roles); cand = [os.environ.get('OLLAMA_BIN'),'/opt/homebrew/bin/ollama','/usr/local/bin/ollama', shutil.which('ollama')]; print('OLLAMA_BIN candidates:', [c for c in cand if c]); print('bind:', os.environ.get('TINYINTENT_BIND','(unset)'), 'port:', os.environ.get('TINYINTENT_PORT','(unset)'))"
