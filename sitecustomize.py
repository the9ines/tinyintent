import os, time, json, subprocess, sys
START_MONO = getattr(sys.modules.get(__name__), "START_MONO", time.monotonic())

def _read_version_sha(project_root):
    version = "dev"
    sha = "unknown"
    try:
        with open(os.path.join(project_root, "VERSION"), "r") as f:
            version = f.read().strip() or "dev"
    except Exception:
        pass
    try:
        out = subprocess.run(["git","rev-parse","--short","HEAD"], cwd=project_root, capture_output=True, text=True)
        if out.returncode == 0:
            sha = out.stdout.strip() or "unknown"
    except Exception:
        pass
    return version, sha

def _env_ok(env):
    def in_set(k, allowed):
        v = env.get(k, "")
        return v in allowed
    reasons = []
    ok = True
    if not env.get("TINYINTENT_SECRET"):
        ok = False; reasons.append("TINYINTENT_SECRET missing")
    if not in_set("TINYINTENT_DRYRUN", {"0","1"}): ok=False; reasons.append("TINYINTENT_DRYRUN not in {0,1}")
    if not in_set("DOUBLE_CHECK", {"0","1"}): ok=False; reasons.append("DOUBLE_CHECK not in {0,1}")
    if not in_set("FORCE_IPHONE", {"0","1"}): ok=False; reasons.append("FORCE_IPHONE not in {0,1}")
    if env.get("LOCAL_MODEL_PREF", "auto") not in {"auto","8b","32b","70b"}:
        ok=False; reasons.append("LOCAL_MODEL_PREF invalid")
    if not in_set("TAILSCALE_ONLY", {"0","1"}): ok=False; reasons.append("TAILSCALE_ONLY not in {0,1}")
    try:
        rps = int(env.get("RATE_LIMIT_RPS","3")); 
        if rps <= 0: ok=False; reasons.append("RATE_LIMIT_RPS <= 0")
    except Exception:
        ok=False; reasons.append("RATE_LIMIT_RPS not int")
    try:
        kb = int(env.get("MAX_BODY_KB","32")); 
        if kb <= 0: ok=False; reasons.append("MAX_BODY_KB <= 0")
    except Exception:
        ok=False; reasons.append("MAX_BODY_KB not int")
    return ok, reasons

def _router_ok(project_root):
    path = os.path.join(project_root, "router", "tinyintent")
    return os.path.exists(path) and os.access(path, os.X_OK)

def _ollama_ok():
    try:
        p = subprocess.run(["ollama","--version"], capture_output=True, text=True, timeout=3)
        return p.returncode == 0
    except Exception:
        return False

def _attach(app):
    from flask import jsonify
    project_root = os.path.dirname(os.path.abspath(__file__))
    version, sha = _read_version_sha(project_root)
    def healthz():
        uptime = time.monotonic() - START_MONO
        return jsonify({
            "status":"ok",
            "uptime_s": round(uptime, 3),
            "version": version,
            "build_sha": sha,
            "tailscale_only": os.environ.get("TAILSCALE_ONLY","0") == "1",
            "rate_limit_rps": int(os.environ.get("RATE_LIMIT_RPS","3")),
            "max_body_kb": int(os.environ.get("MAX_BODY_KB","32")),
            "local_model_pref": os.environ.get("LOCAL_MODEL_PREF","auto"),
        }), 200
    def readyz():
        env_ok, env_reasons = _env_ok(os.environ)
        checks = {
            "env_valid": env_ok,
            "router_binary": _router_ok(project_root),
            "ollama_present": _ollama_ok(),
        }
        ready = all(checks.values())
        reasons = []
        if not env_ok: reasons.extend(env_reasons)
        if not checks["router_binary"]: reasons.append("router binary missing or not executable")
        if not checks["ollama_present"]: reasons.append("ollama not present")
        status = 200 if ready else 503
        return jsonify({
            "ready": ready,
            "reasons": reasons,
            "checks": checks,
            "privacy": "local_only",
            "version": version,
            "build_sha": sha,
        }), status
    # register routes if not already present
    try:
        app.add_url_rule("/healthz", "healthz", healthz, methods=["GET"])
    except Exception:
        pass
    try:
        app.add_url_rule("/readyz", "readyz", readyz, methods=["GET"])
    except Exception:
        pass

# Try common app locations and attach
APP_CANDIDATES = [
    ("bridge.server","app"),
    ("bridge.app","app"),
]
for modname, attr in APP_CANDIDATES:
    try:
        mod = __import__(modname, fromlist=[attr])
        app = getattr(mod, attr, None)
        if app is not None:
            _attach(app)
            break
    except Exception:
        continue
