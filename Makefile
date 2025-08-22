# TinyIntent Makefile
# Implements build targets for M1-M3 milestones

# Default target
.DEFAULT_GOAL := help

# Project configuration
PROJECT_ROOT := $(shell pwd)
ROUTER_DIR := $(PROJECT_ROOT)/router
BRIDGE_DIR := $(PROJECT_ROOT)/bridge
DATA_DIR := $(PROJECT_ROOT)/data

# Swift configuration
SWIFT := swift
SWIFT_FLAGS := -O

# Python configuration
PYTHON := python3

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

##@ Help
help: ## Display this help
	@echo "TinyIntent v2 - Make Targets"
	@echo "============================="
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Development
bridgesrv: ## Start the Bridge API service
	@echo "$(GREEN)Starting TinyIntent Bridge Service...$(NC)"
	@cd $(BRIDGE_DIR) && TINYINTENT_SECRET=${TINYINTENT_SECRET} $(PYTHON) tinyrpc.py

health: ## Show basic model/hardware readiness (quick check)
	@echo "$(GREEN)TinyIntent System Health Check$(NC)"
	@echo "================================"
	@echo "Project root: $(PROJECT_ROOT)"
	@echo ""
	@echo "📁 Directory structure:"
	@test -d $(ROUTER_DIR) && echo "  ✅ router/" || echo "  ❌ router/ (missing)"
	@test -d $(BRIDGE_DIR) && echo "  ✅ bridge/" || echo "  ❌ bridge/ (missing)"
	@test -d $(DATA_DIR) && echo "  ✅ data/" || echo "  ❌ data/ (missing)"
	@echo ""
	@echo "🔧 Dependencies:"
	@which swift > /dev/null && echo "  ✅ Swift compiler available" || echo "  ❌ Swift compiler missing"
	@which $(PYTHON) > /dev/null && echo "  ✅ Python3 available" || echo "  ❌ Python3 missing"
	@which ollama > /dev/null && echo "  ✅ Ollama available" || echo "  ❌ Ollama missing"
	@echo ""
	@echo "📊 Models:"
	@test -f $(ROUTER_DIR)/SmallIntent.mlmodel && echo "  ✅ SmallIntent.mlmodel present" || echo "  ❌ SmallIntent.mlmodel missing (run 'make router-train')"
	@test -f $(ROUTER_DIR)/data/intents.tsv && echo "  ✅ Training data present" || echo "  ❌ Training data missing"
	@echo ""
	@echo "💾 Model configuration:"
	@test -f models.yaml && cat models.yaml || echo "  ❌ models.yaml missing"

##@ Router (M3)
router-train: ## Train the SmallIntent model and produce CoreML artifacts
	@echo "$(GREEN)Training SmallIntent Router Model...$(NC)"
	@echo "==================================="
	@test -f $(ROUTER_DIR)/data/intents.tsv || (echo "$(RED)Error: Training data not found at $(ROUTER_DIR)/data/intents.tsv$(NC)" && exit 1)
	@echo "$(YELLOW)Step 1: Training PyTorch model...$(NC)"
	@cd $(PROJECT_ROOT) && $(PYTHON) $(ROUTER_DIR)/train/train.py
	@echo "$(YELLOW)Step 2: Exporting to ONNX...$(NC)"
	@cd $(PROJECT_ROOT) && $(PYTHON) $(ROUTER_DIR)/train/export_onnx.py
	@echo "$(YELLOW)Step 3: Converting to CoreML (SmallIntent.mlmodel + TinyIntent.mlmodel)...$(NC)"
	@cd $(PROJECT_ROOT) && $(PYTHON) $(ROUTER_DIR)/train/convert_coreml_direct.py
	@echo "$(YELLOW)Step 4: Validating model artifacts...$(NC)"
	@test -f $(ROUTER_DIR)/SmallIntent.mlmodel || (echo "$(RED)Error: SmallIntent.mlmodel not created$(NC)" && exit 1)
	@test -f $(ROUTER_DIR)/TinyIntent.mlmodel || (echo "$(RED)Error: TinyIntent.mlmodel not created$(NC)" && exit 1)
	@test -f $(ROUTER_DIR)/train_summary.json || (echo "$(RED)Error: train_summary.json not created$(NC)" && exit 1)
	@echo "$(GREEN)✅ Router training and CoreML artifacts completed!$(NC)"
	@echo "$(GREEN)  - SmallIntent.mlmodel (high-capacity model, 70-85MB target)$(NC)"
	@echo "$(GREEN)  - TinyIntent.mlmodel (mobile target, ≤5MB)$(NC)"
	@echo "$(GREEN)  - train_summary.json (API endpoint data)$(NC)"

router-eval: ## Evaluate the trained router model
	@echo "$(GREEN)Evaluating SmallIntent Router Model...$(NC)"
	@echo "====================================="
	@test -f $(ROUTER_DIR)/SmallIntent.mlmodel || (echo "$(RED)Error: Model not found. Run 'make router-train' first.$(NC)" && exit 1)
	@echo "$(YELLOW)Running CoreML model evaluation...$(NC)"
	@cd $(PROJECT_ROOT) && $(PYTHON) $(ROUTER_DIR)/eval_router.py
	@echo "$(GREEN)✅ Router evaluation completed!$(NC)"

router-clean: ## Clean router build artifacts
	@echo "$(YELLOW)Cleaning router artifacts...$(NC)"
	@rm -f $(ROUTER_DIR)/SmallIntent.mlmodel
	@rm -f $(ROUTER_DIR)/*.mlmodel
	@echo "$(GREEN)✅ Router artifacts cleaned$(NC)"

##@ Learning Loop (M5.3)
learn: ## Automated learning loop: export episodes → train → evaluate → validate artifacts
	@echo "$(GREEN)Starting TinyIntent Learning Loop...$(NC)"
	@echo "=================================="
	@echo "$(YELLOW)Step 1: Exporting episodes to training data...$(NC)"
	@$(PYTHON) scripts/export_episodes.py
	@echo ""
	@echo "$(YELLOW)Step 2: Training router model and producing CoreML artifacts...$(NC)"
	@$(MAKE) router-train
	@echo ""
	@echo "$(YELLOW)Step 3: Evaluating trained model...$(NC)"
	@$(MAKE) router-eval
	@echo ""
	@echo "$(YELLOW)Step 4: Validating complete learning pipeline...$(NC)"
	@test -f $(ROUTER_DIR)/SmallIntent.mlmodel && echo "  ✅ SmallIntent.mlmodel ready" || echo "  ❌ SmallIntent.mlmodel missing"
	@test -f $(ROUTER_DIR)/TinyIntent.mlmodel && echo "  ✅ TinyIntent.mlmodel ready" || echo "  ❌ TinyIntent.mlmodel missing"
	@test -f $(ROUTER_DIR)/train_summary.json && echo "  ✅ Training summary available" || echo "  ❌ Training summary missing"
	@test -f $(ROUTER_DIR)/data/eval_results.json && echo "  ✅ Evaluation results available" || echo "  ❌ Evaluation results missing"
	@echo ""
	@echo "$(GREEN)✅ Learning loop completed with versioned CoreML artifacts!$(NC)"
	@echo "$(GREEN)Access training status via: GET /router/train_summary$(NC)"

learn-dry: ## M7.5: Dry-run learning loop analysis without training
	@echo "$(GREEN)Starting TinyIntent Learning Loop (DRY RUN)...$(NC)"
	@echo "=============================================="
	@echo "$(YELLOW)🔍 Analyzing episodes and training readiness...$(NC)"
	@$(PYTHON) scripts/export_episodes.py --dry-run
	@echo ""
	@echo "$(YELLOW)💡 Next steps if satisfied with analysis:$(NC)"
	@echo "  1. Run 'make learn' for actual training"
	@echo "  2. Check GET /router/train_summary for results"
	@echo ""
	@echo "$(GREEN)✅ Learning loop dry-run completed!$(NC)"

promote: ## Promote evaluated model to active use if it meets criteria
	@echo "$(GREEN)Promoting Router Model...$(NC)"
	@echo "========================="
	@test -f $(ROUTER_DIR)/data/eval_results.json || (echo "$(RED)Error: No evaluation results found. Run 'make router-eval' first.$(NC)" && exit 1)
	@$(PYTHON) scripts/promote_model.py
	@echo "$(GREEN)✅ Model promotion completed!$(NC)"

autopilot: ## Run full continuous learning cycle: learn → promote
	@echo "$(GREEN)Starting TinyIntent Autopilot...$(NC)"
	@echo "==============================="
	@$(PYTHON) scripts/autopilot.py
	@echo "$(GREEN)✅ Autopilot cycle completed!$(NC)"

autopilot-dry: ## Run autopilot in dry-run mode (no promotion)
	@echo "$(GREEN)Starting TinyIntent Autopilot (DRY RUN)...$(NC)"
	@echo "=========================================="
	@$(PYTHON) scripts/autopilot.py --dry-run
	@echo "$(GREEN)✅ Autopilot dry run completed!$(NC)"

export-episodes: ## Export episodes to training data
	@echo "$(GREEN)Exporting episodes to training data...$(NC)"
	@$(PYTHON) scripts/export_episodes.py
	@echo "$(GREEN)✅ Episodes exported$(NC)"

export-summary: ## Show episode export summary
	@echo "$(GREEN)Episode Export Summary$(NC)"
	@echo "====================="
	@$(PYTHON) scripts/export_episodes.py --summary

##@ Data Management
clean-data: ## Clean episode data (DANGEROUS)
	@echo "$(RED)⚠️  This will delete all episode data!$(NC)"
	@read -p "Are you sure? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	@rm -rf $(DATA_DIR)/episodes/*
	@echo "$(GREEN)✅ Episode data cleaned$(NC)"

backup-data: ## Backup episode data
	@echo "$(GREEN)Backing up episode data...$(NC)"
	@mkdir -p backups
	@tar -czf backups/episodes-$(shell date +%Y%m%d-%H%M%S).tar.gz $(DATA_DIR)/episodes/
	@echo "$(GREEN)✅ Episode data backed up$(NC)"

##@ Development Tools
lint: ## Run ruff linting on Python code
	@echo "$(GREEN)Running ruff linting...$(NC)"
	@ruff check . || echo "$(YELLOW)Install ruff with: pip install ruff$(NC)"

format: ## Format code with ruff
	@echo "$(GREEN)Formatting code with ruff...$(NC)"
	@ruff format . || echo "$(YELLOW)Install ruff with: pip install ruff$(NC)"

typecheck: ## Run mypy type checking
	@echo "$(GREEN)Running mypy type checking...$(NC)"
	@mypy . || echo "$(YELLOW)Install mypy with: pip install mypy$(NC)"

test: ## Run pytest tests
	@echo "$(GREEN)Running pytest tests...$(NC)"
	@pytest tests/ -v || echo "$(YELLOW)Install pytest with: pip install pytest$(NC)"

doctor: ## Run local CI and system health checks
	@echo "$(GREEN)Running TinyIntent Doctor...$(NC)"
	@echo "============================"
	@$(PYTHON) scripts/ci_local.py
	@$(PYTHON) scripts/doctor.py

doctor-json: ## Run doctor and output JSON results path
	@echo "$(GREEN)Running TinyIntent Doctor (JSON output)...$(NC)"
	@$(PYTHON) scripts/doctor.py
	@echo "$(GREEN)JSON results saved to:$(NC) $(PROJECT_ROOT)/bridge/logs/doctor.json"

##@ Utilities
clean: router-clean ## Clean all build artifacts
	@echo "$(GREEN)✅ All artifacts cleaned$(NC)"

status: ## Show project status
	@echo "$(GREEN)TinyIntent Project Status$(NC)"
	@echo "========================="
	@echo "Git status:"
	@git status --porcelain || echo "Not a git repository"
	@echo ""
	@echo "Recent activity:"
	@ls -la $(DATA_DIR)/episodes/ 2>/dev/null || echo "No episode data"

.PHONY: help bridgesrv doctor router-train router-eval router-clean learn promote autopilot autopilot-dry export-episodes export-summary clean-data backup-data lint format test clean status