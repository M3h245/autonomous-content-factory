#!/usr/bin/env python3
"""Probe the current machine and write capabilities.json.

Nothing is assumed: every capability is marked available only after a live probe succeeds.
Credentials are reported by *name only* (present / absent); values are never read into output.

  python doctor.py --out capabilities.json [--deep]
"""
from __future__ import annotations

import argparse
import importlib
import os
import platform
import re
import shutil
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import cache_dir, now_iso, run, skills_root, write_json, ffmpeg_bin  # noqa: E402

KOKORO_LANGS = {"en-us": "a", "en-gb": "b", "es": "e", "fr-fr": "f", "hi": "h", "it": "i", "pt-br": "p", "ja": "j", "zh": "z"}
NEEDED_FILTERS = ["ass", "zoompan", "xfade", "loudnorm", "ebur128", "sidechaincompress", "blackdetect",
                  "freezedetect", "silencedetect", "alimiter"]
SERVICES = {  # host -> capability it unlocks
    "api.elevenlabs.io": "tts.elevenlabs", "api.openai.com": "tts.openai / visual.image_api.openai",
    "www.googleapis.com": "trends.youtube_data / publish.youtube", "youtubeanalytics.googleapis.com": "analytics.youtube_api",
    "api.pexels.com": "visual.stock.pexels", "pixabay.com": "visual.stock.pixabay", "huggingface.co": "models.huggingface",
    "open.tiktokapis.com": "publish.tiktok", "graph.facebook.com": "publish.instagram",
}
CREDENTIALS = ["ELEVENLABS_API_KEY", "OPENAI_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY", "YOUTUBE_API_KEY",
               "YOUTUBE_OAUTH_CLIENT_SECRETS", "TIKTOK_ACCESS_TOKEN", "IG_ACCESS_TOKEN", "ANTHROPIC_API_KEY"]


def probe_http(url: str, timeout: float = 5.0) -> str:
    req = urllib.request.Request(url, method="HEAD")
    try:
        urllib.request.urlopen(req, timeout=timeout)
        return "reachable"
    except urllib.error.HTTPError as e:
        if e.code == 403 and "host_not_allowed" in str(e.headers.get("x-deny-reason", "")):
            return "blocked_by_sandbox"
        return "reachable"  # any HTTP answer from the service itself means egress works
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
        return "unreachable"


IMPORT_ERRORS: dict = {}


def module_version(name: str):
    try:
        m = importlib.import_module(name)
        return getattr(m, "__version__", "installed")
    except Exception as exc:  # noqa: BLE001 — keep the reason: "installed but cannot load" needs a different fix
        IMPORT_ERRORS[name] = f"{type(exc).__name__}: {exc}"[:300]
        return None


def import_fix(mod: str, pkg: str) -> str:
    """Install hint for a module that is missing or installed but unable to load (Phase 5: skia-python was installed but
    could not load libEGL.so.1, so the doodle engine was unavailable while setup reported success)."""
    err = IMPORT_ERRORS.get(mod, "")
    m = re.search(r"(lib[\w.+-]+\.so[\w.]*)", err)
    if m:
        apt = {"libEGL.so.1": "libegl1", "libGL.so.1": "libgl1", "libfontconfig.so.1": "libfontconfig1",
               "libsndfile.so.1": "libsndfile1"}.get(m.group(1), m.group(1).split(".so")[0])
        return f"{pkg} is installed but cannot load {m.group(1)}: Debian/Ubuntu `sudo apt-get install -y {apt}`"
    return f"pip install {pkg}" + (f" ({err})" if err else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="capabilities.json")
    ap.add_argument("--deep", action="store_true", help="load the TTS model to confirm phoneme timings")
    ap.add_argument("--forge-url", default=os.environ.get("CF_FORGE_URL", "http://127.0.0.1:7860"))
    a = ap.parse_args()

    tools: dict = {"python": platform.python_version(), "os": platform.platform(), "cpus": os.cpu_count()}
    ff = shutil.which(ffmpeg_bin())
    tools["ffmpeg"] = bool(ff)
    filters: list[str] = []
    if ff:
        out = run([ff, "-hide_banner", "-filters"], check=False).stdout
        present = {ln.split()[1] for ln in out.splitlines() if len(ln.split()) > 2}
        filters = [f for f in NEEDED_FILTERS if f in present]
        tools["ffmpeg_version"] = run([ff, "-hide_banner", "-version"], check=False).stdout.split("\n")[0]
    tools["ffmpeg_filters_missing"] = [f for f in NEEDED_FILTERS if f not in filters]
    tess = shutil.which("tesseract")
    tools["tesseract_langs"] = run([tess, "--list-langs"], check=False).stdout.split()[4:] if tess else []
    tools["rsvg_convert"] = bool(shutil.which("rsvg-convert"))
    for mod in ["numpy", "PIL", "fontTools", "soundfile", "onnxruntime", "kokoro_onnx", "cv2", "pandas", "cairosvg", "pytesseract",
                "skia", "svgelements", "arabic_reshaper", "bidi"]:
        tools[f"py.{mod}"] = module_version(mod)

    kdir = cache_dir() / "kokoro"
    kmodel, kvoices = kdir / "kokoro-v1.0.onnx", kdir / "voices-v1.0.bin"
    kokoro = {"model": kmodel.exists(), "voices": kvoices.exists(), "timings": None}
    if a.deep and kmodel.exists() and tools["py.kokoro_onnx"]:
        from kokoro_onnx import Kokoro
        kokoro["timings"] = Kokoro(str(kmodel), str(kvoices)).has_timings
    tools["kokoro"] = kokoro

    fonts_dir = skills_root() / "subtitle-production" / "assets" / "fonts"
    tools["bundled_fonts"] = sorted(p.name for p in fonts_dir.glob("*.ttf")) if fonts_dir.exists() else []

    network = {host: probe_http(f"https://{host}") for host in SERVICES}
    forge = probe_http(a.forge_url.rstrip("/") + "/sdapi/v1/sd-models", timeout=2.0)
    creds = {k: bool(os.environ.get(k)) for k in CREDENTIALS}

    def egress(host):
        return network.get(host) == "reachable"

    render_ok = bool(ff) and not tools["ffmpeg_filters_missing"]
    caps = {
        "tts.kokoro": {"available": bool(tools["py.kokoro_onnx"] and kokoro["model"] and kokoro["voices"]),
                       "languages": sorted(KOKORO_LANGS), "word_timing": "model phoneme durations" if kokoro["timings"] in (True, None) else "none",
                       "fix": "python setup_env.py"},
        "tts.elevenlabs": {"available": creds["ELEVENLABS_API_KEY"] and egress("api.elevenlabs.io"), "word_timing": "character alignment"},
        "tts.openai": {"available": creds["OPENAI_API_KEY"] and egress("api.openai.com"), "word_timing": "estimated"},
        "visual.doodle": {"available": bool(tools["py.skia"] and tools["py.svgelements"] and tools["py.numpy"]),
                          "note": "v2 animated doodle engine (video-production/scripts/doodle_engine.py)",
                          "fix": "; ".join(import_fix(m, p) for m, p in (("skia", "skia-python"), ("svgelements", "svgelements"),
                                                                         ("numpy", "numpy")) if not tools[f"py.{m}"]) or None},
        "visual.svg": {"available": tools["rsvg_convert"] or bool(tools["py.cairosvg"])},
        "visual.procedural": {"available": bool(tools["py.numpy"] and tools["py.PIL"])},
        "visual.sd_forge": {"available": forge == "reachable", "url": a.forge_url,
                            "fix": "start WebUI Forge with --api on this machine"},
        "visual.image_api.openai": {"available": creds["OPENAI_API_KEY"] and egress("api.openai.com")},
        "visual.stock.pexels": {"available": creds["PEXELS_API_KEY"] and egress("api.pexels.com")},
        "visual.stock.pixabay": {"available": creds["PIXABAY_API_KEY"] and egress("pixabay.com")},
        "video.render": {"available": render_ok},
        "subtitles.burn": {"available": render_ok and "ass" in filters and bool(tools["bundled_fonts"])},
        "qa.probes": {"available": render_ok},
        "qa.ocr": {"available": bool(tools["tesseract_langs"]), "langs": tools["tesseract_langs"],
                   "fix": None if tools["tesseract_langs"] else "recommended (reviewer and caption OCR checks): Debian/Ubuntu "
                   "`sudo apt-get install -y tesseract-ocr`, macOS `brew install tesseract`, Windows `winget install UB-Mannheim.TesseractOCR`"},
        "trends.youtube_data": {"available": creds["YOUTUBE_API_KEY"] and egress("www.googleapis.com")},
        "analytics.youtube_api": {"available": creds["YOUTUBE_OAUTH_CLIENT_SECRETS"] and egress("youtubeanalytics.googleapis.com")},
        "analytics.csv_import": {"available": bool(tools["py.pandas"])},
        "publish.youtube_api": {"available": False, "note": "never autonomous: requires OAuth + explicit human approval per upload"},
        "research.web": {"available": "agent-tool", "note": "web_search/web_fetch are Claude tools; not probed from the shell"},
    }
    tools["import_errors"] = dict(IMPORT_ERRORS)
    report = {"generated_at": now_iso(), "tools": tools, "network": network, "local_services": {"sd_forge": forge},
              "credentials_present": creds, "capabilities": caps}
    write_json(a.out, report)
    on = sorted(k for k, v in caps.items() if v["available"] is True)
    off = sorted(k for k, v in caps.items() if v["available"] is False)
    print(f"capabilities available: {', '.join(on)}\nunavailable: {', '.join(off)}\nwritten: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
