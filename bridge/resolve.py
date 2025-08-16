import shutil, os, subprocess

CANDIDATES = [
    lambda: os.environ.get("OLLAMA_BIN"),
    lambda: "/opt/homebrew/bin/ollama",
    lambda: "/usr/local/bin/ollama",
    lambda: shutil.which("ollama"),
]

def resolve_ollama_path():
    tried = []
    for provider in CANDIDATES:
        p = provider()
        if not p: 
            continue
        tried.append(p)
        if shutil.which(p) or os.path.isfile(p):
            return p, tried
    return None, tried

def check_ollama_ok(path):
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=3)
        return out.returncode == 0
    except Exception:
        return False
