#!/usr/bin/env python3
import os, sys, json, time, subprocess, hashlib, ipaddress
from typing import Dict, Any
from flask import Flask, request, jsonify
from collections import defaultdict
import re

# Router v2 labels
ROUTER_V2_LABELS = {"gen", "act"}
LABELS = {"plan_then_local", "local_only"}  # Keep for internal compatibility
MAX_TEXT = 8192
MAX_CONTENT_LENGTH = 40000

SECRET = os.getenv("TINYINTENT_SECRET")
PORT = int(os.getenv("TINYINTENT_PORT", "8787"))
BIND = os.getenv("TINYINTENT_BIND", "127.0.0.1")
ALLOW_LAN = os.getenv("ALLOW_LAN", "0") == "1"
BIN = os.getenv("TINYINTENT_BIN", "/Users/oberfelder/projects/smallintent/router/tinyintent")
AGENT = os.getenv("NEURO_AGENT", "/Users/oberfelder/projects/smallintent/agent/neuro_agent")
DRY = os.getenv("TINYINTENT_DRYRUN", "0") == "1"
DOUBLE_CHECK = os.getenv("DOUBLE_CHECK", "0") == "1"
FORCE_IPHONE = os.getenv("FORCE_IPHONE", "0") == "1"
LOG_PATH = os.getenv("LOG_PATH", "/Users/oberfelder/projects/smallintent/bridge/logs/tinyrpc.log")

# New M4.1 environment variables
TAILSCALE_ONLY = os.getenv("TAILSCALE_ONLY", "0") == "1"
RATE_LIMIT_RPS = float(os.getenv("RATE_LIMIT_RPS", "3"))
MAX_BODY_KB = int(os.getenv("MAX_BODY_KB", "32"))

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_BODY_KB * 1024

# Simple token bucket rate limiter
class RateLimiter:
    def __init__(self, rate: float):
        self.rate = rate
        self.buckets = defaultdict(lambda: {"tokens": rate, "last_refill": time.time()})
    
    def allow(self, key: str) -> bool:
        now = time.time()
        bucket = self.buckets[key]
        
        # Refill bucket based on elapsed time
        elapsed = now - bucket["last_refill"]
        bucket["tokens"] = min(self.rate, bucket["tokens"] + elapsed * self.rate)
        bucket["last_refill"] = now
        
        # Check if request is allowed
        if bucket["tokens"] >= 1.0:
            bucket["tokens"] -= 1.0
            return True
        return False

rate_limiter = RateLimiter(RATE_LIMIT_RPS)

def is_tailscale_ip(ip: str) -> bool:
    """Check if IP is in Tailscale range 100.64.0.0/10"""
    try:
        ip_obj = ipaddress.ip_address(ip)
        tailscale_net = ipaddress.ip_network("100.64.0.0/10")
        return ip_obj in tailscale_net
    except ValueError:
        return False

def log_line(msg: str) -> None:
    line = f"[tinyrpc] {time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, file=sys.stderr, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def error(status: int, message: str):
    log_line(f"err status={status} msg={message!r}")
    return jsonify({"error": message}), status

def sanity_check():
    # Fatal checks at startup
    if not SECRET or SECRET == "CHANGE_ME_SECRET":
        log_line("fatal: TINYINTENT_SECRET not set or still placeholder")
        sys.stderr.write("TINYINTENT_SECRET required and must not be CHANGE_ME_SECRET\n")
        sys.stderr.flush()
        os._exit(1)
    
    # Network binding security
    if BIND == "0.0.0.0" and not ALLOW_LAN:
        log_line("fatal: TINYINTENT_BIND=0.0.0.0 requires ALLOW_LAN=1")
        sys.stderr.write("TINYINTENT_BIND=0.0.0.0 requires ALLOW_LAN=1\n")
        sys.stderr.flush()
        os._exit(1)
    
    # Warnings for missing binaries
    if not os.path.isfile(BIN):
        log_line(f"warn: classifier not found at {BIN}")
    if not os.path.isfile(AGENT):
        log_line(f"warn: neuro_agent not found at {AGENT}")

@app.before_request
def validate_request():
    # Content-Type validation
    if request.method == "POST" and request.content_type != "application/json":
        return error(415, "Content-Type must be application/json")
    
    # Content-Length validation  
    if request.content_length and request.content_length > MAX_BODY_KB * 1024:
        return error(413, "payload_too_large")

@app.post("/route")
def route():
    remote_addr = request.remote_addr or "unknown"
    tailscale = is_tailscale_ip(remote_addr)
    
    # Auth check
    hdr = request.headers.get("X-TinyIntent-Secret", "")
    if not SECRET or hdr != SECRET:
        log_line(f"remote_addr={remote_addr} tailscale={tailscale} allowed=false status=err msg=unauthorized")
        return error(401, "unauthorized")
    
    # Tailscale-only check
    if TAILSCALE_ONLY and not tailscale:
        log_line(f"remote_addr={remote_addr} tailscale={tailscale} allowed=false status=err msg=tailscale_required")
        return error(403, "tailscale_required")
    
    # Rate limiting
    if not rate_limiter.allow(remote_addr):
        log_line(f"remote_addr={remote_addr} tailscale={tailscale} allowed=false status=err msg=rate_limited")
        return error(429, "rate_limited")

    # Parse JSON
    try:
        payload: Dict[str, Any] = request.get_json(force=True, silent=False)
    except Exception:
        return error(400, "invalid JSON")
    if not isinstance(payload, dict):
        return error(400, "invalid payload")

    text = str(payload.get("text", "") or "").strip()
    route_label = str(payload.get("route", "auto") or "auto").strip()
    
    body_size_kb = len(text.encode('utf-8')) / 1024
    text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]

    if not text or len(text) > MAX_TEXT:
        return error(400, "text missing or too long")
    
    mapped_from = None
    
    # Handle route classification and pattern-based legacy mapping
    if route_label == "auto":
        # Call router binary to classify into gen/act
        if os.path.isfile(BIN):
            try:
                proc = subprocess.run([BIN], input=text, text=True, capture_output=True, timeout=30)
                if proc.returncode == 0:
                    route_label = proc.stdout.strip()
                    if route_label not in ROUTER_V2_LABELS:
                        log_line(f"router_classification_invalid: {route_label} -> gen")
                        route_label = "gen"
                else:
                    log_line(f"router_classification_failed: rc={proc.returncode} -> gen")
                    route_label = "gen"
            except Exception as e:
                log_line(f"router_classification_error: {e} -> gen")
                route_label = "gen"
        else:
            log_line(f"router_binary_missing: {BIN} -> gen")
            route_label = "gen"
    
    # Pattern-based legacy mapping (avoid literal tokens)
    elif route_label not in ROUTER_V2_LABELS:
        original_route = route_label
        if re.match(r'^send_', route_label, re.IGNORECASE):
            route_label = "gen"
            mapped_from = original_route
            log_line(f"legacy_pattern_mapping: {original_route} -> gen")
        elif re.match(r'^plan_then_', route_label, re.IGNORECASE):
            route_label = "act"
            mapped_from = original_route
            log_line(f"legacy_pattern_mapping: {original_route} -> act")
        else:
            return error(400, f"invalid route label: {route_label}")

    orig_label = route_label
    iphone_label = route_label
    mac_label = None
    
    # Optional double-check on Mac
    if DOUBLE_CHECK and os.path.isfile(BIN):
        try:
            proc = subprocess.run([BIN], input=text, text=True, capture_output=True, timeout=30)
            if proc.returncode == 0:
                mac_label = proc.stdout.strip()
                if mac_label in LABELS and mac_label != route_label and not FORCE_IPHONE:
                    route_label = mac_label
                    log_line(f"double_check mismatch: iphone={iphone_label} mac={mac_label} chosen={route_label}")
                elif mac_label not in LABELS:
                    log_line(f"double_check invalid mac_label={mac_label!r}; using iphone={orig_label}")
            else:
                log_line(f"double_check classifier error rc={proc.returncode}")
        except Exception as e:
            log_line(f"double_check exception: {e}")

    # Build agent command
    args = [AGENT]
    if DRY:
        args.append("--dry-run")

    # Build environment with route, source, and remote context
    env = dict(os.environ)
    # Map Router v2 labels to agent-compatible ones
    agent_route = "local_only" if route_label == "gen" else "plan_then_local" if route_label == "act" else route_label
    env["ROUTE"] = agent_route
    env["TEXT_SOURCE"] = "iphone"
    env["REMOTE_ADDR"] = remote_addr
    env["TAILSCALE"] = "true" if tailscale else "false"
    env["BODY_SIZE_KB"] = str(int(body_size_kb))

    # Call agent with route and text
    try:
        agent = subprocess.run(args, input=text, text=True, capture_output=True, timeout=60, env=env)
    except Exception as e:
        return error(500, f"agent failed: {e}")

    ok = agent.returncode == 0
    status = "ok" if ok else "err"
    allowed = True
    
    log_line(f"remote_addr={remote_addr} tailscale={tailscale} len={len(text)} hash={text_hash} route={route_label} body_size_kb={int(body_size_kb)} allowed={allowed} dry={1 if DRY else 0} status={status} privacy=local_only")

    if not ok:
        return error(500, agent.stderr.strip() or "agent error")

    # Build response with optional double-check info
    response = {
        "ok": True,
        "route_label": route_label,
        "stdout": agent.stdout,
        "privacy": "local_only"
    }
    
    if mapped_from:
        response["mapped_from"] = mapped_from
    
    if DOUBLE_CHECK and mac_label:
        response["iphone_route"] = iphone_label
        response["mac_route"] = mac_label
        response["chosen_route"] = route_label

    return jsonify(response), 200

if __name__ == "__main__":
    sanity_check()
    log_line(f"starting bind={BIND} port={PORT} dry={1 if DRY else 0} tailscale_only={TAILSCALE_ONLY} rate_limit={RATE_LIMIT_RPS} max_body_kb={MAX_BODY_KB}")
    app.run(host=BIND, port=PORT)