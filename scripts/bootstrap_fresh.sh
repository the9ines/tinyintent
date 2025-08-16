#!/usr/bin/env bash
# TinyIntent M0 Fresh Boot Bootstrap
# Creates .venv, installs deps, rotates secret, configures plist, and starts bridge

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[BOOTSTRAP]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

cd "$PROJECT_ROOT"

echo "==========================================="
echo -e "${BLUE}TinyIntent M0 Fresh Boot Bootstrap${NC}"
echo "==========================================="

# Step 1: Create .venv if missing
log "Step 1: Setting up Python virtual environment"
BRIDGE_DIR="bridge"
VENV_PATH="$BRIDGE_DIR/.venv"

if [[ ! -d "$VENV_PATH" ]]; then
    log "Creating virtual environment at $VENV_PATH"
    python3 -m venv "$VENV_PATH"
else
    log "Virtual environment already exists at $VENV_PATH"
fi

# Activate venv and install dependencies
log "Installing Flask and dependencies"
source "$VENV_PATH/bin/activate"

# Upgrade pip first
pip install -U pip >/dev/null 2>&1

# Install requirements
if [[ -f "$BRIDGE_DIR/requirements_bridge.txt" ]]; then
    pip install -r "$BRIDGE_DIR/requirements_bridge.txt" >/dev/null 2>&1
else
    # Minimal requirements for M0
    pip install Flask jsonschema >/dev/null 2>&1
fi

success "Python environment ready"

# Step 2: Generate fresh secret
log "Step 2: Generating fresh secret"
# Generate 24-character alphanumeric secret
SECRET=$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 24)
log "Generated 24-character secret"

# Step 3: Configure plist
log "Step 3: Configuring launchd plist"
PLIST_PATH="launchd/com.tinyintent.tinyrpc.plist"
SAMPLE_PATH="launchd/com.tinyintent.tinyrpc.sample.plist"

# Copy sample to real plist if it doesn't exist
if [[ ! -f "$PLIST_PATH" ]]; then
    if [[ -f "$SAMPLE_PATH" ]]; then
        cp "$SAMPLE_PATH" "$PLIST_PATH"
        log "Copied sample plist to $PLIST_PATH"
    else
        error "Sample plist not found at $SAMPLE_PATH"
    fi
fi

# Detect Ollama path
log "Detecting Ollama installation"
OLLAMA_PATH=""
for candidate in "$HOME/.local/bin/ollama" "/opt/homebrew/bin/ollama" "/usr/local/bin/ollama" "$(command -v ollama 2>/dev/null || echo "")"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
        OLLAMA_PATH="$candidate"
        break
    fi
done

if [[ -z "$OLLAMA_PATH" ]]; then
    warn "Ollama not found in standard locations"
    OLLAMA_PATH="/opt/homebrew/bin/ollama"  # default guess
else
    log "Found Ollama at: $OLLAMA_PATH"
fi

# Configure environment variables in plist
log "Setting environment variables in plist"

# Set PATH (important for launchd)
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:PATH $PROJECT_ROOT/.venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:PATH string $PROJECT_ROOT/.venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" "$PLIST_PATH"

# Set TINYINTENT_SECRET
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:TINYINTENT_SECRET $SECRET" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:TINYINTENT_SECRET string $SECRET" "$PLIST_PATH"

# Set TINYINTENT_BIND (0.0.0.0 for phone access)
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:TINYINTENT_BIND 0.0.0.0" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:TINYINTENT_BIND string 0.0.0.0" "$PLIST_PATH"

# Set TINYINTENT_PORT
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:TINYINTENT_PORT 8787" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:TINYINTENT_PORT string 8787" "$PLIST_PATH"

# Set TINYINTENT_DRYRUN
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:TINYINTENT_DRYRUN 0" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:TINYINTENT_DRYRUN string 0" "$PLIST_PATH"

# Set LOCAL_MODEL_PREF
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:LOCAL_MODEL_PREF auto" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:LOCAL_MODEL_PREF string auto" "$PLIST_PATH"

# Set DOUBLE_CHECK
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:DOUBLE_CHECK 1" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:DOUBLE_CHECK string 1" "$PLIST_PATH"

# Set FORCE_IPHONE
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:FORCE_IPHONE 0" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:FORCE_IPHONE string 0" "$PLIST_PATH"

# Set TAILSCALE_ONLY
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:TAILSCALE_ONLY 0" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:TAILSCALE_ONLY string 0" "$PLIST_PATH"

# Set OLLAMA_BIN
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:OLLAMA_BIN $OLLAMA_PATH" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:OLLAMA_BIN string $OLLAMA_PATH" "$PLIST_PATH"

success "Plist configured with environment variables"

# Step 4: Restart bridge service
log "Step 4: Starting TinyIntent bridge service"

# Stop any existing service
if launchctl list | grep -q com.tinyintent.tinyrpc; then
    log "Stopping existing bridge service"
    launchctl unload -w "$PLIST_PATH" 2>/dev/null || true
    sleep 1
fi

# Start service
log "Loading bridge service"
launchctl load -w "$PLIST_PATH"
sleep 2

# Check if service started
if launchctl list | grep -q com.tinyintent.tinyrpc; then
    success "Bridge service started successfully"
else
    warn "Bridge service may not have started properly"
fi

# Step 5: Print connection info
echo
echo "==========================================="
echo -e "${GREEN}TinyIntent M0 Bootstrap Complete!${NC}"
echo "==========================================="

# Get network info
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "unknown")
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "not available")

echo
echo -e "${BLUE}Connection Information:${NC}"
echo "Secret: $SECRET"
echo
echo "URLs:"
echo "  Localhost: http://127.0.0.1:8787"
echo "  LAN:       http://$LAN_IP:8787"
if [[ "$TAILSCALE_IP" != "not available" ]]; then
    echo "  Tailscale: http://$TAILSCALE_IP:8787"
fi

echo
echo -e "${BLUE}Quick Test:${NC}"
echo "  bash tests/health.sh"
echo "  echo \"summarize tinyintent\" | bin/ti -r auto --json"

echo
echo -e "${BLUE}iPhone Shortcut Setup:${NC}"
echo "  URL: http://$LAN_IP:8787/route"
echo "  Header: X-TinyIntent-Secret"
echo "  Value: $SECRET"
echo "  Body: {\"text\":\"[DICTATED_TEXT]\",\"route\":\"auto\"}"

echo
echo -e "${BLUE}Logs:${NC}"
echo "  make bridge-logs"

echo "==========================================="