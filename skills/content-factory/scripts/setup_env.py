#!/usr/bin/env python3
"""Bootstrap this machine for the Content Factory (idempotent, safe to re-run at the start of every session).

  python setup_env.py [--out capabilities.json]

1. installs missing Python packages (kokoro-onnx, soundfile, numpy, pillow, fonttools, pandas, and for the v2 doodle
   engine: skia-python, svgelements, arabic-reshaper, python-bidi — all ship prebuilt wheels for Windows/macOS/Linux)
2. downloads the Kokoro TTS model into the cache (GitHub release, ~354 MB, once per machine/session)
3. runs doctor.py so every capability claim is verified on THIS machine
ffmpeg must be installed separately: Windows `winget install Gyan.FFmpeg`, macOS `brew install ffmpeg`,
Debian/Ubuntu `sudo apt-get install -y ffmpeg`.
"""
from __future__ import annotations

import argparse
import importlib
import platform
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import skill_script  # noqa: E402

# Pinned audio runtime (Phase 3 finding: an unpinned reinstall shifted Kokoro output by up to 8 ms → not byte-reproducible
# across machines). Reference versions verified 2026-10-07; the TTS cache key and timing.json record them.
PKGS = {"onnxruntime": "onnxruntime==1.29.0", "kokoro_onnx": "kokoro-onnx==0.6.1", "soundfile": "soundfile", "numpy": "numpy", "PIL": "pillow",
        "fontTools": "fonttools", "pandas": "pandas", "skia": "skia-python", "svgelements": "svgelements",
        "arabic_reshaper": "arabic-reshaper", "bidi": "python-bidi"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="capabilities.json")
    a = ap.parse_args()
    missing = []
    for mod, pkg in PKGS.items():
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        cmd = [sys.executable, "-m", "pip", "install", "--quiet", *missing]
        if Path(sysconfig.get_paths()["stdlib"], "EXTERNALLY-MANAGED").exists() and sys.prefix == sys.base_prefix:
            cmd.append("--break-system-packages")
        print("installing:", " ".join(missing))
        subprocess.run(cmd, check=True)
    subprocess.run([sys.executable, str(skill_script("voice-production", "tts.py")), "setup"], check=True)
    if not shutil.which("ffmpeg"):
        hint = {"Windows": "winget install Gyan.FFmpeg", "Darwin": "brew install ffmpeg"}.get(platform.system(),
                                                                                             "sudo apt-get install -y ffmpeg")
        print(f"ffmpeg not found — install it: {hint}")
    return subprocess.run([sys.executable, str(Path(__file__).with_name("doctor.py")), "--out", a.out]).returncode


if __name__ == "__main__":
    sys.exit(main())
