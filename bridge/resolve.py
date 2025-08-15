import os, shutil, subprocess, json

DEFAULT_CANDIDATES = [
    lambda: os.environ.get("OLLAMA_BIN", "").strip() or None,
    lambda: "/opt/homebrew/bin/ollama",
    lambda: "/usr/local/bin/ollama",
    lambda: shutil.which("ollama"),
]

def resolve_ollama_path():
    tried = []
    for getter in DEFAULT_CANDIDATES:
        try:
            candidate = getter()
        except Exception:
            candidate = None
        if not candidate:
            continue
        tried.append(candidate)
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate, tried
    return None, tried

def check_ollama_ok(ollama_path, timeout=3):
    if not ollama_path:
        return False, "not_found"
    try:
        p = subprocess.run([ollama_path, "--version"], capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0, ("rc=%s" % p.returncode)
    except Exception as e:
        return False, str(e)