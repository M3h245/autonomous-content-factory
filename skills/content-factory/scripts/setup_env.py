#!/usr/bin/env python3
"""Bootstrap this machine for the Content Factory (idempotent, safe to re-run at the start of every session).

  python setup_env.py [--out capabilities.json]

1. installs missing Python packages (kokoro-onnx, soundfile, numpy, pillow, fonttools, pandas, and for the v2 doodle
   engine: skia-python, svgelements, arabic-reshaper, python-bidi — all ship prebuilt wheels for Windows/macOS/Linux)
2. downloads the Kokoro TTS model into the cache (GitHub release, ~354 MB, once per machine/session)
3. runs doctor.py so every capability claim is verified on THIS machine; exits 3 (with the fix) if a core capability
   (narration, rendering, captions, doodle visuals) is unavailable
ffmpeg must be installed separately: Windows `winget install Gyan.FFmpeg`, macOS `brew install ffmpeg`,
Debian/Ubuntu `sudo apt-get install -y ffmpeg`.
"""
from __future__ import annotations

import argparse
import importlib
import json
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
        if "==" in pkg:              # Phase 5: a pin is enforced, not only applied when the package is absent
            from importlib.metadata import PackageNotFoundError, version
            name, want = pkg.split("==")
            try:
                if version(name) != want:
                    missing.append(pkg)
                continue
            except PackageNotFoundError:
                missing.append(pkg)
                continue
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
    rc = subprocess.run([sys.executable, str(Path(__file__).with_name("doctor.py")), "--out", a.out]).returncode
    if rc != 0:
        return rc
    # Phase 5: never report success on a machine that cannot produce the default video (skia-python once failed to load
    # libEGL.so.1, the doodle engine was unavailable, and setup still exited 0)
    caps = json.loads(Path(a.out).read_text(encoding="utf-8"))["capabilities"]
    core = {"tts.kokoro": "narration", "video.render": "rendering", "subtitles.burn": "captions", "visual.doodle": "doodle visuals"}
    bad = [k for k in core if caps.get(k, {}).get("available") is not True]
    for k in bad:
        print(f"MISSING CORE CAPABILITY {k} ({core[k]}): {caps.get(k, {}).get('fix') or 'see doctor output'}")
    if caps.get("qa.ocr", {}).get("available") is not True:
        print(f"recommended: qa.ocr — {caps.get('qa.ocr', {}).get('fix')}")
    return 3 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
