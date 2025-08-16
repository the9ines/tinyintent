#!/usr/bin/env python3
import os, shutil, sys, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PACKAGE = ROOT / "router" / "TinyIntent.mlpackage"
SRC_MODEL = ROOT / "router" / "TinyIntent.mlmodel"

def main():
    # Try .mlpackage first, then fall back to .mlmodel
    if SRC_PACKAGE.exists():
        src = SRC_PACKAGE
        dst = ROOT / "router" / "TinyIntent_iOS.mlpackage"
    elif SRC_MODEL.exists():
        src = SRC_MODEL
        dst = ROOT / "router" / "TinyIntent_iOS.mlmodel"
    else:
        print(f"[export_ios_model] missing: {SRC_PACKAGE} or {SRC_MODEL}", file=sys.stderr)
        sys.exit(1)
    
    # For v1 we assume TinyIntent model (or TinyIntent.mlpackage) is already ANE/8-bit suitable for iOS Shortcuts.
    # If future: add coremltools re-save with specific target. For now, just copy.
    if os.path.isdir(src):
        # Copy directory (mlpackage)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        # Copy file (mlmodel)
        shutil.copyfile(src, dst)
    
    # Use du -sh for accurate size reporting
    try:
        result = subprocess.run(['du', '-sh', dst], capture_output=True, text=True, check=True)
        size_str = result.stdout.split()[0]
        print(f"[export_ios_model] wrote {dst} ({size_str})")
    except subprocess.CalledProcessError:
        # Fallback to Python calculation
        if os.path.isdir(dst):
            size = sum(os.path.getsize(os.path.join(dirpath, filename))
                      for dirpath, dirnames, filenames in os.walk(dst)
                      for filename in filenames) / (1024*1024)
        else:
            size = os.path.getsize(dst) / (1024*1024)
        print(f"[export_ios_model] wrote {dst} ({size:.2f} MB)")

if __name__ == "__main__":
    main()