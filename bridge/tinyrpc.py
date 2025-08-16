#!/usr/bin/env python3
import os
import sys
import json
import time
import subprocess
import hashlib
import ipaddress
from typing import Dict, Any
from flask import Flask, request, jsonify
from pathlib import Path

# Add project root to Python path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from bridge.resolve import resolve_ollama_path, check_ollama_ok

# Configuration
SECRET = os.getenv("TINYINTENT_SECRET")
PORT = int(os.getenv("TINYINTENT_PORT", "8787"))
BIND = os.getenv("TINYINTENT_BIND", "127.0.0.1")
BIN = os.getenv("TINYINTENT_BIN", str(PROJECT_ROOT / "router" / "tinyintent"))
AGENT = os.getenv("NEURO_AGENT", str(PROJECT_ROOT / "agent" / "neuro_agent"))
DRY = os.getenv("TINYINTENT_DRYRUN", "0") == "1"
LOCAL_MODEL_PREF = os.getenv("LOCAL_MODEL_PREF", "auto")
DOUBLE_CHECK = os.getenv("DOUBLE_CHECK", "1") == "1"
FORCE_IPHONE = os.getenv("FORCE_IPHONE", "0") == "1"
ALLOW_DEV_LOCAL = os.getenv("ALLOW_DEV_LOCAL", "0") == "1"
TAILSCALE_ONLY = os.getenv("TAILSCALE_ONLY", "0") == "1"
RATE_LIMIT_RPS = float(os.getenv("RATE_LIMIT_RPS", "3"))
MAX_BODY_KB = int(os.getenv("MAX_BODY_KB", "32"))

MAX_TEXT = 8192

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_BODY_KB * 1024

# Record start time for uptime calculation
START_MONO = time.monotonic()

def is_localhost_ip(ip: str) -> bool:
    """Check if IP is localhost (127.0.0.1 or ::1)"""
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_loopback
    except ValueError:
        return False

def log_line(msg: str) -> None:
    line = f"[tinyrpc] {time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, file=sys.stderr, flush=True)

def error(status: int, message: str):
    log_line(f"err status={status} msg={message!r}")
    return jsonify({"error": message}), status

def read_version_sha():
    """Read version and git SHA for health endpoints"""
    version = "dev"
    build_sha = "unknown"
    
    # Try to read VERSION file
    try:
        version_path = PROJECT_ROOT / "VERSION"
        if version_path.is_file():
            with open(version_path, 'r') as f:
                version = f.read().strip()
    except Exception:
        pass
    
    # Try to get git SHA
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            cwd=PROJECT_ROOT
        )
        if proc.returncode == 0:
            build_sha = proc.stdout.strip()
    except Exception:
        pass
    
    return version, build_sha

def env_ok():
    """Check if environment variables are valid"""
    try:
        # Check required secret
        if not SECRET or SECRET == "CHANGE_ME_SECRET":
            return False
        
        # Check model preference
        if LOCAL_MODEL_PREF not in {"auto", "8b", "32b", "70b"}:
            return False
        
        # Check numeric values
        if RATE_LIMIT_RPS <= 0 or MAX_BODY_KB <= 0:
            return False
        
        return True
    except Exception:
        return False

def router_ok():
    """Check if router binary exists and is executable"""
    return os.path.isfile(BIN) and os.access(BIN, os.X_OK)

def ollama_ok():
    """Check if ollama is available"""
    ollama_path, _ = resolve_ollama_path()
    if not ollama_path:
        return False
    
    ok, _ = check_ollama_ok(ollama_path)
    return ok

@app.get("/healthz")
def healthz():
    version, build_sha = read_version_sha()
    uptime_s = time.monotonic() - START_MONO
    
    return jsonify({
        "status": "ok",
        "uptime_s": uptime_s,
        "version": version,
        "build_sha": build_sha,
        "tailscale_only": TAILSCALE_ONLY,
        "rate_limit_rps": int(RATE_LIMIT_RPS),
        "max_body_kb": MAX_BODY_KB,
        "local_model_pref": LOCAL_MODEL_PREF
    })

@app.get("/readyz")
def readyz():
    version, build_sha = read_version_sha()
    
    checks = {
        "env_valid": env_ok(),
        "router_binary": router_ok(),
        "ollama_present": ollama_ok()
    }
    
    ready = all(checks.values())
    reasons = []
    
    if not checks["env_valid"]:
        reasons.append("Environment validation failed")
    if not checks["router_binary"]:
        reasons.append("Router binary not found or not executable")
    if not checks["ollama_present"]:
        reasons.append("Ollama not available")
    
    response = {
        "ready": ready,
        "reasons": reasons,
        "checks": checks,
        "privacy": "local_only",
        "version": version,
        "build_sha": build_sha
    }
    
    return jsonify(response), 200 if ready else 503

def check_auth(remote_addr: str) -> tuple[bool, str]:
    """Check authentication for the request. Returns (allowed, reason)"""
    # Get secret from environment
    secret = os.getenv("TINYINTENT_SECRET", "").strip()
    
    # Get header (case-insensitive) and trim whitespace
    header_value = ""
    for key, value in request.headers:
        if key.lower() == "x-tinyintent-secret":
            header_value = value.strip()
            break
    
    # Check if secret is configured
    if not secret:
        return False, "secret_not_configured"
    
    # Check for dev bypass (localhost only)
    if ALLOW_DEV_LOCAL and is_localhost_ip(remote_addr):
        if not header_value:  # No header provided
            # Additional hardening checks
            forwarded_for = request.headers.get("X-Forwarded-For")
            host_header = request.headers.get("Host", "").lower()
            
            # Only allow if no X-Forwarded-For and Host is localhost-like
            if (forwarded_for is None and 
                (host_header.startswith("localhost") or 
                 host_header.startswith("127.0.0.1") or 
                 host_header.startswith("::1") or
                 host_header.split(':')[0] in ["localhost", "127.0.0.1", "::1"])):
                return True, "dev_bypass"
    
    # Check if header is missing/empty
    if not header_value:
        return False, "missing_header"
    
    # Check if header matches secret
    if header_value != secret:
        return False, "mismatch"
    
    # Success with secret
    return True, "secret_ok"

@app.before_request
def validate_request():
    # Skip auth for health endpoints
    if request.path in ["/healthz", "/readyz"]:
        return None
    
    # Auth check for all other endpoints
    remote_addr = request.remote_addr or "unknown"
    allowed, reason = check_auth(remote_addr)
    
    if not allowed:
        log_line(f"allowed=false reason={reason}")
        
        if reason == "secret_not_configured":
            return jsonify({"error": "unauthorized", "code": "secret_not_configured"}), 401
        elif reason == "mismatch":
            # Get lengths for detail
            secret = os.getenv("TINYINTENT_SECRET", "").strip()
            header_value = ""
            for key, value in request.headers:
                if key.lower() == "x-tinyintent-secret":
                    header_value = value.strip()
                    break
            
            return jsonify({
                "error": "unauthorized",
                "code": "mismatch", 
                "detail": {
                    "provided_len": len(header_value),
                    "expected_len": len(secret)
                }
            }), 401
        else:  # missing_header
            return jsonify({"error": "unauthorized", "code": "missing_header"}), 401

@app.post("/route")
def route():
    remote_addr = request.remote_addr or "unknown"

    # Parse JSON
    try:
        payload: Dict[str, Any] = request.get_json(force=True, silent=False)
    except Exception:
        return error(400, "invalid JSON")
    if not isinstance(payload, dict):
        return error(400, "invalid payload")

    text = str(payload.get("text", "") or "").strip()
    route_label = str(payload.get("route", "auto") or "auto").strip()
    
    text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]

    if not text or len(text) > MAX_TEXT:
        return error(400, "text missing or too long")

    # Handle route classification
    router_fallback = None
    if route_label == "auto":
        # Try router binary first
        if router_ok():
            try:
                proc = subprocess.run([BIN], input=text, text=True, capture_output=True, timeout=30)
                if proc.returncode == 0:
                    route_label = proc.stdout.strip()
                    if route_label not in {"gen", "act"}:
                        log_line(f"router_classification_invalid: {route_label} -> heuristic")
                        route_label = "auto"  # Reset to trigger heuristic
                else:
                    # Detailed logging for failed router
                    bytes_out = len(proc.stdout)
                    bytes_err = len(proc.stderr)
                    reason = proc.stderr.split('\n')[0] if proc.stderr.strip() else 'unknown'
                    log_line(f"[router] rc={proc.returncode} bytes_out={bytes_out} bytes_err={bytes_err} reason={reason}")
                    router_fallback = {"rc": proc.returncode, "reason": reason, "mode": "heuristic"}
                    route_label = "auto"  # Reset to trigger heuristic
            except Exception as e:
                log_line(f"router_classification_error: {e} -> heuristic")
                router_fallback = {"rc": -1, "reason": str(e), "mode": "heuristic"}
                route_label = "auto"  # Reset to trigger heuristic
        
        # If still auto (router missing/failed/invalid), use heuristic
        if route_label == "auto":
            if not router_ok():
                log_line(f"router_binary_missing: {BIN} -> heuristic")
                router_fallback = {"rc": -1, "reason": "binary_missing", "mode": "heuristic"}
            # Fallback heuristic: action keywords -> act, else gen
            action_keywords = ["restart", "tail", "sell", "start", "stop", "logs", "errors", "run", "execute", "deploy", "build"]
            if any(keyword in text.lower() for keyword in action_keywords):
                route_label = "act"
            else:
                route_label = "gen"

    # Validate route
    if route_label not in {"gen", "act"}:
        return error(400, f"invalid route label: {route_label}")

    # Resolve ollama path
    ollama_path, tried_paths = resolve_ollama_path()
    log_line(f"deps.ollama_path={ollama_path or 'none'} tried={len(tried_paths)}")
    
    if not ollama_path:
        return jsonify({
            "error": "missing_dependency",
            "dep": "ollama", 
            "code": "not_found",
            "tried": tried_paths,
            "hint": "Set OLLAMA_BIN or extend PATH in launchd plist"
        }), 500

    # Handle act route as preview-only
    if route_label == "act":
        # Return preview JSON without execution
        response = {
            "action": "preview",
            "params": {"text": text[:100] + "..." if len(text) > 100 else text},
            "summary": f"Would execute action based on: '{text[:50]}{'...' if len(text) > 50 else ''}'",
            "confirm_required": True
        }
        if router_fallback:
            response["_router_fallback"] = router_fallback
        return jsonify(response), 200

    # Handle gen route with Ollama
    if route_label == "gen":
        try:
            # Simple Ollama call for local generation
            models = ["qwen2.5:32b-instruct-q4_K_M", "llama3.1:8b-instruct-q5_K_M"]
            for model in models:
                try:
                    start_time = time.time()
                    proc = subprocess.run([
                        ollama_path, "run", model, text
                    ], capture_output=True, text=True, timeout=60)
                    
                    if proc.returncode == 0:
                        latency_ms = int((time.time() - start_time) * 1000)
                        response_text = proc.stdout.strip()
                        
                        # Log success
                        log_line(f"remote_addr={remote_addr} len={len(text)} hash={text_hash} route={route_label} model={model} latency_ms={latency_ms} privacy=local_only")
                        
                        response = {
                            "text": response_text,
                            "model": model,
                            "latency_ms": latency_ms
                        }
                        if router_fallback:
                            response["_router_fallback"] = router_fallback
                        return jsonify(response), 200
                except Exception as e:
                    log_line(f"model {model} failed: {e}")
                    continue
            
            # All models failed
            return error(500, "all local models failed")
            
        except Exception as e:
            return error(500, f"generation failed: {e}")

    return error(400, "invalid route")

if __name__ == "__main__":
    # Startup checks
    if not SECRET or SECRET == "CHANGE_ME_SECRET":
        log_line("fatal: TINYINTENT_SECRET not set or still placeholder")
        sys.stderr.write("TINYINTENT_SECRET required and must not be CHANGE_ME_SECRET\n")
        sys.stderr.flush()
        os._exit(1)
    
    log_line(f"listening host={BIND} port={PORT}")
    app.run(host=BIND, port=PORT)