import os, time, json, socket, sqlite3, hashlib, ipaddress, threading, yaml, subprocess
from flask import Flask, request, jsonify
from jsonschema import validate, ValidationError

APP_START = time.time()
VERSION = "dev"
BUILD_SHA = os.environ.get("BUILD_SHA","")

BIND = os.environ.get("TINYINTENT_BIND","127.0.0.1")
PORT = int(os.environ.get("TINYINTENT_PORT","8787"))
LOCAL_MODEL_PREF = os.environ.get("LOCAL_MODEL_PREF","auto")
RATE_LIMIT_RPS = int(os.environ.get("RATE_LIMIT_RPS","3"))
MAX_BODY_KB = int(os.environ.get("MAX_BODY_KB","32"))
SECRET = os.environ.get("TINYINTENT_SECRET")
ALLOW_DEV_LOCAL = os.environ.get("ALLOW_DEV_LOCAL","0") == "1"

DATA_DIR = "data/episodes"
NDJSON_PATH = os.path.join(DATA_DIR, "events.ndjson")
DB_PATH = os.path.join(DATA_DIR, "events.db")

from .resolve import resolve_ollama_path, check_ollama_ok

app = Flask(__name__)

# ---- model registry ----
DEFAULT_ROLES = {
  "small":  "llama3.1:8b-instruct-q5_K_M",
  "medium": "qwen2.5:32b-instruct-q4_K_M",
  "large":  "llama3.1:70b-instruct-q4_K_M",
}
_registry = {"roles": DEFAULT_ROLES.copy()}
_registry_mtime = 0
_registry_lock = threading.Lock()

def _load_registry():
    global _registry, _registry_mtime
    try:
        st = os.stat("models.yaml")
        mtime = int(st.st_mtime)
        if mtime == _registry_mtime: 
            return
        with open("models.yaml","r") as f:
            data = yaml.safe_load(f) or {}
        roles = data.get("roles") or {}
        eff = DEFAULT_ROLES.copy()
        eff.update({k:v for k,v in roles.items() if isinstance(v,str) and v})
        with _registry_lock:
            _registry = {"roles": eff}
            _registry_mtime = mtime
    except FileNotFoundError:
        with _registry_lock:
            _registry = {"roles": DEFAULT_ROLES.copy()}
            _registry_mtime = 0

def _effective_mapping():
    _load_registry()
    roles = dict(_registry["roles"])
    # env overrides
    e_small = os.environ.get("MODEL_SMALL")
    e_med   = os.environ.get("MODEL_MEDIUM")
    e_large = os.environ.get("MODEL_LARGE")
    if e_small: roles["small"] = e_small
    if e_med:   roles["medium"]= e_med
    if e_large: roles["large"] = e_large
    return roles

def _localhost_only():
    ra = request.remote_addr or ""
    try:
        ip = ipaddress.ip_address(ra)
        return ip.is_loopback
    except Exception:
        return False

@app.route("/admin/reload-models", methods=["POST"])
def reload_models():
    if not _localhost_only():
        return jsonify({"error":"forbidden","code":"localhost_only"}), 403
    _load_registry()
    return jsonify({"ok":True,"effective_roles":_effective_mapping()})

# ---- experience store ----
EVENT_KEYS = ["ts","session_id","text","route_pred","route_final","model_used",
              "latency_ms","preview_json","executed","success","feedback","error_code","labels","hash"]

os.makedirs(DATA_DIR, exist_ok=True)

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL, session_id TEXT, text TEXT, route_pred TEXT, route_final TEXT,
        model_used TEXT, latency_ms REAL, preview_json TEXT, executed INTEGER,
        success INTEGER, feedback TEXT, error_code TEXT, labels TEXT, hash TEXT
    );""")
    conn.commit()
    return conn

def _append_event(ev):
    line = json.dumps(ev, ensure_ascii=False)
    with open(NDJSON_PATH,"a", encoding="utf-8") as f:
        f.write(line+"\n")
    conn = _db()
    conn.execute("""INSERT INTO events(ts,session_id,text,route_pred,route_final,model_used,
        latency_ms,preview_json,executed,success,feedback,error_code,labels,hash)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ev["ts"],ev["session_id"],ev["text"],ev["route_pred"],ev["route_final"],ev["model_used"],
         ev["latency_ms"],json.dumps(ev["preview_json"]) if ev["preview_json"] is not None else None,
         1 if ev["executed"] else 0,
         None if ev["success"] is None else (1 if ev["success"] else 0),
         ev["feedback"],ev["error_code"],json.dumps(ev["labels"]),ev["hash"]))
    conn.commit()
    conn.close()

@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json(force=True, silent=True) or {}
    eid = data.get("episode_id"); success = data.get("success"); fb = data.get("feedback")
    if not isinstance(eid,int):
        return jsonify({"error":"bad_request","code":"missing_or_invalid_episode_id"}), 400
    conn = _db()
    cur = conn.execute("SELECT id FROM events WHERE id=?", (eid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error":"not_found"}), 404
    conn.execute("UPDATE events SET success=?, feedback=? WHERE id=?",
                 (None if success is None else (1 if success else 0), fb, eid))
    conn.commit(); conn.close()
    return jsonify({"ok":True})

# ---- auth ----
def _authorized():
    if request.method == "GET" and request.path in ("/healthz","/readyz"):
        return True
    hdr = request.headers.get("X-TinyIntent-Secret")
    if hdr is None:
        return False, "missing_header"
    if not SECRET:
        return False, "secret_not_configured"
    if hdr != SECRET:
        return False, "mismatch"
    return True, None

# ---- ollama helpers ----
def _resolve_ollama():
    p, tried = resolve_ollama_path()
    ok = p and check_ollama_ok(p)
    return p, tried, ok

def _choose_model_tag(text, llm_pref=None, llm_model=None):
    if llm_model: return llm_model
    roles = _effective_mapping()
    if llm_pref in ("small","medium","large"):
        return roles[llm_pref]
    # auto heuristic: short->small, medium->medium, long->large
    n = len((text or "").split())
    if n <= 25: return roles["small"]
    if n <= 120: return roles["medium"]
    return roles["large"]

def _ollama_gen(tag, prompt):
    path, tried, ok = _resolve_ollama()
    if not ok:
        return None, {"error":"missing_dependency","dep":"ollama","code":"not_found","tried":tried,
                      "hint":"Install via Homebrew and/or set OLLAMA_BIN in LaunchAgent"}
    t0 = time.time()
    try:
        proc = subprocess.run([path,"run",tag, prompt], capture_output=True, text=True, timeout=120)
        latency = int((time.time()-t0)*1000)
        if proc.returncode != 0:
            return None, {"error":"ollama_error","code":proc.returncode,"stderr":proc.stderr}
        return {"text":proc.stdout.strip(), "model":tag, "latency_ms":latency}, None
    except subprocess.TimeoutExpired:
        return None, {"error":"timeout","dep":"ollama"}
    except Exception as e:
        return None, {"error":"exception","detail":str(e)}

# ---- schemas ----
ACT_SCHEMA = {
  "type":"object",
  "required":["action","params","summary","confirm_required"],
  "properties":{
    "action":{"type":"string","minLength":1},
    "params":{"type":"object"},
    "summary":{"type":"string"},
    "confirm_required":{"type":"boolean"}
  },
  "additionalProperties": False
}

# ---- endpoints ----
@app.route("/healthz")
def healthz():
    return jsonify({
        "status":"ok",
        "version": VERSION,
        "build_sha": BUILD_SHA,
        "uptime_s": time.time()-APP_START,
        "tailscale_only": False,
        "rate_limit_rps": RATE_LIMIT_RPS,
        "max_body_kb": MAX_BODY_KB,
        "local_model_pref": LOCAL_MODEL_PREF
    })

@app.route("/readyz")
def readyz():
    path, tried, ok = _resolve_ollama()
    roles = _effective_mapping()
    # check installed models
    missing = []
    if ok:
        try:
            out = subprocess.run([path, "list"], capture_output=True, text=True, timeout=5)
            have = out.stdout
            for role, tag in roles.items():
                if tag.split()[0] not in have:
                    missing.append(tag)
        except Exception:
            pass
    checks = {
        "env_valid": True,
        "ollama_present": bool(ok),
        "models_present": ok and len(missing)==0
    }
    ready = all(checks.values())
    return jsonify({
        "ready": ready,
        "checks": checks,
        "missing_models": missing,
        "reasons": ([] if ready else ["dependencies_missing_or_models_absent"]),
        "version": VERSION,
        "build_sha": BUILD_SHA
    }), (200 if ready else 503)

@app.route("/route", methods=["POST"])
def route():
    ok, code = _authorized() if SECRET else (False, "secret_not_configured")
    if ok is not True:
        return jsonify({"error":"unauthorized","code":code}), 401

    body = request.get_json(force=True, silent=True) or {}
    text = body.get("text","")
    route = body.get("route","auto")
    llm_pref = body.get("llm_pref")
    llm_model = body.get("llm_model")

    # simple heuristic until router lands
    pred = "act" if any(k in text.lower() for k in ["restart","tail","log","sell","close position","errors","update","ssh","bot"]) else "gen"
    final = route if route in ("gen","act") else pred

    # gen
    if final == "gen":
        tag = _choose_model_tag(text, llm_pref, llm_model)
        out, err = _ollama_gen(tag, text)
        resp = (out if out else err)
    else:
        # act preview only
        preview = {
            "action":"guess_command",
            "params":{"raw": text},
            "summary":"Preview only. No execution in M1/M2.",
            "confirm_required": True
        }
        try:
            validate(instance=preview, schema=ACT_SCHEMA)
            resp = preview
        except ValidationError as e:
            return jsonify({"error":"bad_request","code":"schema_validation","detail":str(e)}), 400

    # episode
    ev = {
      "ts": time.time(),
      "session_id": hashlib.sha1((request.remote_addr or "local").encode()).hexdigest()[:12],
      "text": text,
      "route_pred": pred,
      "route_final": final,
      "model_used": (resp.get("model") if isinstance(resp,dict) else None),
      "latency_ms": (resp.get("latency_ms") if isinstance(resp,dict) else None),
      "preview_json": (resp if final=="act" else None),
      "executed": False,
      "success": None,
      "feedback": None,
      "error_code": (resp.get("error") if isinstance(resp,dict) and "error" in resp else None),
      "labels": [],
      "hash": hashlib.sha1((text or "").encode()).hexdigest()
    }
    _append_event(ev)

    # add fallback hint if we used heuristic
    if route == "auto":
        if final == pred:
            if final in ("gen","act"):
                if isinstance(resp, dict):
                    resp["_router_fallback"] = {"mode":"heuristic"}

    # one-line log
    try:
        model = resp.get("model") if isinstance(resp,dict) else "-"
        latency = resp.get("latency_ms") if isinstance(resp,dict) else "-"
        app.logger.info(f"remote={request.remote_addr} route={final} model={model} latency_ms={latency}")
    except Exception:
        pass

    return jsonify(resp)

def run():
    app.run(host=BIND, port=PORT, threaded=True)

if __name__ == "__main__":
    run()
