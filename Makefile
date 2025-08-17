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

doctor: ## Show model/hardware readiness
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
router-train: ## Train the SmallIntent model
	@echo "$(GREEN)Training SmallIntent Router Model...$(NC)"
	@echo "==================================="
	@test -f $(ROUTER_DIR)/data/intents.tsv || (echo "$(RED)Error: Training data not found at $(ROUTER_DIR)/data/intents.tsv$(NC)" && exit 1)
	@cd $(PROJECT_ROOT) && chmod +x $(ROUTER_DIR)/train_router.swift
	@cd $(PROJECT_ROOT) && $(SWIFT) $(ROUTER_DIR)/train_router.swift
	@echo "$(GREEN)✅ Router training completed!$(NC)"

router-eval: ## Evaluate the trained router model
	@echo "$(GREEN)Evaluating SmallIntent Router Model...$(NC)"
	@echo "====================================="
	@test -f $(ROUTER_DIR)/SmallIntent.mlmodel || (echo "$(RED)Error: Model not found. Run 'make router-train' first.$(NC)" && exit 1)
	@cd $(PROJECT_ROOT) && chmod +x $(ROUTER_DIR)/eval_router.swift
	@cd $(PROJECT_ROOT) && $(SWIFT) $(ROUTER_DIR)/eval_router.swift
	@echo "$(GREEN)✅ Router evaluation completed!$(NC)"

router-clean: ## Clean router build artifacts
	@echo "$(YELLOW)Cleaning router artifacts...$(NC)"
	@rm -f $(ROUTER_DIR)/SmallIntent.mlmodel
	@rm -f $(ROUTER_DIR)/*.mlmodel
	@echo "$(GREEN)✅ Router artifacts cleaned$(NC)"

##@ Learning Loop (M5.3)
learn: ## Automated learning loop: export episodes → train → evaluate
	@echo "$(GREEN)Starting TinyIntent Learning Loop...$(NC)"
	@echo "=================================="
	@echo "$(YELLOW)Step 1: Exporting episodes to training data...$(NC)"
	@$(PYTHON) scripts/export_episodes.py
	@echo ""
	@echo "$(YELLOW)Step 2: Training router model...$(NC)"
	@$(MAKE) router-train
	@echo ""
	@echo "$(YELLOW)Step 3: Evaluating trained model...$(NC)"
	@$(MAKE) router-eval
	@echo ""
	@echo "$(GREEN)✅ Learning loop completed!$(NC)"

promote: ## Promote evaluated model to active use if it meets criteria
	@echo "$(GREEN)Promoting Router Model...$(NC)"
	@echo "========================="
	@test -f $(ROUTER_DIR)/data/eval_results.json || (echo "$(RED)Error: No evaluation results found. Run 'make router-eval' first.$(NC)" && exit 1)
	@$(PYTHON) scripts/promote_model.py
	@echo "$(GREEN)✅ Model promotion completed!$(NC)"

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
lint: ## Run code linting (if tools available)
	@echo "$(GREEN)Running code linting...$(NC)"
	@cd $(BRIDGE_DIR) && $(PYTHON) -m py_compile *.py && echo "✅ Python syntax OK" || echo "❌ Python syntax errors"

format: ## Format code (if tools available)  
	@echo "$(GREEN)Formatting code...$(NC)"
	@echo "$(YELLOW)Manual code formatting required$(NC)"

test: ## Run basic smoke tests
	@echo "$(GREEN)Running smoke tests...$(NC)"
	@cd $(BRIDGE_DIR) && TINYINTENT_SECRET=test $(PYTHON) -c "import tinyrpc; print('✅ Bridge imports OK')" || echo "❌ Bridge import failed"
	@test -f $(ROUTER_DIR)/data/intents.tsv && echo "✅ Training data present" || echo "❌ Training data missing"

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

.PHONY: help bridgesrv doctor router-train router-eval router-clean learn promote export-episodes export-summary clean-data backup-data lint format test clean status