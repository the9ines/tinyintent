#!/usr/bin/env python3
import os, sys, json, time, subprocess
from typing import Dict, Any
from flask import Flask, request, jsonify

LABELS = {"send_claude", "plan_then_claude", "local_only"}
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

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

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
    return jsonify({"ok": False, "error": message}), status

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
    if request.content_length and request.content_length > MAX_CONTENT_LENGTH:
        return error(413, "Request too large")

@app.post("/route")
def route():
    # Auth
    hdr = request.headers.get("X-TinyIntent-Secret", "")
    if not SECRET or hdr != SECRET:
        return error(401, "unauthorized")

    # Parse JSON
    try:
        payload: Dict[str, Any] = request.get_json(force=True, silent=False)
    except Exception:
        return error(400, "invalid JSON")
    if not isinstance(payload, dict):
        return error(400, "invalid payload")

    text = str(payload.get("text", "") or "").strip()
    route_label = str(payload.get("route", "") or "").strip()

    if not text or len(text) > MAX_TEXT:
        return error(400, "text missing or too long")
    if route_label not in LABELS:
        return error(400, "invalid route label")

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

    # Build environment with route and source
    env = dict(os.environ)
    env["ROUTE"] = route_label
    env["TEXT_SOURCE"] = "iphone"

    # Call agent with route and text
    try:
        agent = subprocess.run(args, input=text, text=True, capture_output=True, timeout=60, env=env)
    except Exception as e:
        return error(500, f"agent failed: {e}")

    ok = agent.returncode == 0
    status = "ok" if ok else "err"
    log_line(f"ip={request.remote_addr} len={len(text)} route={route_label} dry={1 if DRY else 0} status={status}")

    if not ok:
        return error(500, agent.stderr.strip() or "agent error")

    # Build response with optional double-check info
    response = {
        "ok": True,
        "route": route_label,
        "stdout": agent.stdout
    }
    
    if DOUBLE_CHECK and mac_label:
        response["iphone_route"] = iphone_label
        response["mac_route"] = mac_label
        response["chosen_route"] = route_label

    return jsonify(response), 200

if __name__ == "__main__":
    sanity_check()
    log_line(f"starting bind={BIND} port={PORT} dry={1 if DRY else 0}")
    app.run(host=BIND, port=PORT)