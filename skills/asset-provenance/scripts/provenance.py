#!/usr/bin/env python3
"""asset-provenance — provenance manifest, license gate, credits and AI-disclosure decision for one video.

  provenance.py build --video-dir RUN/videos/v01 --final RUN/videos/v01/subtitles/final.mp4
                      --out-dir RUN/package/v01 --result RUN/package/v01/provenance_result.json
                      [--dossier RUN/research/dossier.json] [--script RUN/videos/v01/script/script.json]
                      [--license-map licenses.json]

Collects the `provenance` records every stage put in its result.json, hashes each asset, blocks anything with an
unknown license or missing attribution, decides per-platform AI labels, writes provenance.json + CREDITS.txt and a
deliverable copy of the video with all internal metadata removed (streams copied, not re-encoded; Phase 3.5 policy).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import (StageResult, emit, exit_for, ffmpeg_bin, fix, now_iso, read_json, run,  # noqa: E402
                       sha256_file, stage_main, write_json)

LICENSE_OK = {"self-generated", "OFL-1.1", "CC0-1.0", "Apache-2.0", "MIT", "Pexels License",
              "Pixabay Content License", "user-owned", "CC-BY-4.0", "commercial-licensed"}
NEEDS_ATTRIBUTION = {"CC-BY-4.0"}
POLICY_BASIS = {"verified": "2026-10-03", "note": "Platform AI-label rules change; re-verify before relying on them. Not legal advice.",
                "youtube": "Label realistic altered/synthetic depictions; AI voiceover alone does not require the label.",
                "tiktok": "Label AI-generated or significantly edited realistic people, scenes, images or audio.",
                "instagram": "Meta labels realistic AI images/audio ('AI info'); disclose photoreal or realistic-sounding synthetic media."}


@stage_main("PACKAGE", "asset-provenance")
def cmd_build(a) -> int:
    vdir, out = Path(a.video_dir).resolve(), Path(a.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    vid = vdir.name
    sr = StageResult("PACKAGE", "asset-provenance", vid)
    lic_map = read_json(a.license_map) if a.license_map else {}
    recs, seen = [], set()
    for res in sorted(vdir.rglob("result.json")):
        for r in read_json(res).get("provenance", []):
            key = (r.get("role"), r.get("path"))
            if key not in seen:
                seen.add(key)
                recs.append(dict(r))
    bad_lic, no_attr, human, consent = [], [], [], []
    for r in recs:
        p = Path(r.get("path", ""))
        if p.is_file():
            r["sha256"], r["bytes"] = sha256_file(p), p.stat().st_size
        model = (r.get("generator") or {}).get("model")
        lic = r.get("license", "unknown")
        if lic == "check model license":
            lic = lic_map.get("models", {}).get(model, lic)
            r["license"] = lic
        if lic == "check model license":
            human.append(f"{r['role']} (model {model})")
        elif lic not in LICENSE_OK:
            bad_lic.append(f"{r['role']}: {lic}")
        if lic in NEEDS_ATTRIBUTION and not r.get("attribution"):
            no_attr.append(r["role"])
        if lic == "commercial-licensed" and not r.get("license_ref"):
            bad_lic.append(f"{r['role']}: commercial-licensed without license_ref")
        if r.get("voice_clone_of_real_person") and not r.get("consent"):
            consent.append(r["role"])
    roles = {r.get("role", "").split(":")[0] for r in recs}
    sr.check("PROV.ASSETS_RECORDED", {"voiceover", "visual"} <= roles, "blocking",
             f"recorded roles {sorted(roles)}", fix=fix("PACKAGE", "rerun_stages_with_provenance"))
    sr.check("PROV.LICENSES_KNOWN", not bad_lic, "blocking", f"unknown/unsupported licenses: {bad_lic}",
             fix=fix("VISUAL_PLAN", "replace_assets", assets=bad_lic), retryable=False)
    sr.check("PROV.ATTRIBUTION", not no_attr, "blocking", f"attribution missing for {no_attr}",
             fix=fix("VISUAL_PLAN", "add_attribution", assets=no_attr))
    sr.check("PROV.MODEL_LICENSE", not human, "major", f"confirm the checkpoint license in licenses.json: {human}",
             retryable=False)
    sr.check("PROV.CONSENT", not consent, "blocking", f"voice clone without recorded consent: {consent}", retryable=False)

    gen_ai = {"sd-webui-forge", "image_api", "video_gen"}
    realistic_visual = any(r.get("role", "").startswith("visual") and r.get("realistic")
                           and (r.get("generator") or {}).get("tool") in gen_ai for r in recs)
    realistic_voice = any(r.get("synthetic_voice") and r.get("realistic_human_voice") for r in recs)
    ai_music = any(r.get("ai_generated_music") for r in recs)
    voice = next((r for r in recs if r.get("role") == "voiceover"), {})
    kinds = sorted({(r.get("generator") or {}).get("tool", r.get("source", "")) for r in recs if r.get("role", "").startswith("visual")})
    disclosure = {
        "youtube": {"altered_or_synthetic": bool(realistic_visual or ai_music),
                    "reason": "realistic synthetic visuals or AI music" if (realistic_visual or ai_music) else "stylized visuals; AI narration alone"},
        "tiktok": {"ai_generated_label": bool(realistic_visual or realistic_voice),
                   "reason": "realistic synthetic voice/visuals (conservative)" if (realistic_visual or realistic_voice) else "none"},
        "instagram": {"ai_info": bool(realistic_visual or realistic_voice)},
        "description_line": (f"Narration: AI text-to-speech ({(voice.get('generator') or {}).get('tool', 'TTS')}). "
                             f"Visuals: {', '.join(kinds) or 'n/a'}."),
        "policy_basis": POLICY_BASIS,
    }
    sources = []
    if a.dossier and a.script:
        d, s = read_json(a.dossier), read_json(a.script)
        used = {cid for b in s["beats"] for cid in b.get("claim_ids", [])}
        sids = {sid for f in d["facts"] if f["id"] in used for sid in f["source_ids"]}
        sources = [{"title": x["title"], "publisher": x.get("publisher"), "url": x["url"]} for x in d["sources"] if x["id"] in sids]
    credits = ["CREDITS", ""]
    for r in recs:
        if r.get("attribution"):
            credits.append(f"- {r['attribution']} ({r.get('license')})")
    for r in recs:
        if r.get("role") == "font":
            credits.append(f"- Font: {Path(r['path']).stem} — {r.get('license')} ({r.get('source')})")
        if r.get("role") == "voiceover":
            g = r.get("generator") or {}
            credits.append(f"- Voice: {g.get('model', g.get('tool'))}, voice '{g.get('voice')}' ({g.get('model_license')})")
        if r.get("role") == "music":
            credits.append(f"- Music: {(r.get('generator') or {}).get('tool', r.get('source'))} ({r.get('license')})")
        if r.get("role") == "sfx":
            credits.append(f"- Sound effects: {(r.get('generator') or {}).get('tool', r.get('source'))} ({r.get('license')})")
    if sources:
        credits += ["", "SOURCES"] + [f"- {x['title']} — {x.get('publisher') or ''} {x['url']}" for x in sources]
    (out / "CREDITS.txt").write_text("\n".join(credits) + "\n", encoding="utf-8")

    deliverable = out / "final.mp4"
    # Phase 3.5 media policy: the publishable file carries no internal provenance/debug metadata. Provenance lives in
    # provenance.json; AI disclosure is applied per platform at upload from metadata.json (labels + description line).
    from media_clean import clean_mp4
    clean_mp4(Path(a.final), deliverable)
    digest = sha256_file(deliverable)
    manifest = {"video_id": vid, "generated_at": now_iso(), "final": {"path": str(deliverable), "sha256": digest,
                "bytes": deliverable.stat().st_size, "source_render_sha256": sha256_file(a.final)},
                "assets": [{k: v for k, v in r.items()} for r in recs], "disclosure": disclosure, "sources": sources}
    for r in manifest["assets"]:
        r.setdefault("sha256", None); r.setdefault("source", "unknown"); r.setdefault("license", "unknown")
    write_json(out / "provenance.json", manifest)
    sr.check("PROV.HASH_VERIFIED", sha256_file(deliverable) == digest, "blocking", "deliverable hash stable after write")
    sr.metric("assets", len(recs)); sr.metric("disclosure", {k: v for k, v in disclosure.items() if k in ("youtube", "tiktok", "instagram")})
    for name, role in [("provenance.json", "provenance"), ("CREDITS.txt", "credits"), ("final.mp4", "deliverable_video")]:
        sr.output(out / name, role)
    res = sr.finalize(a.result)
    emit(res)
    return exit_for(res)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    for k in ("--video-dir", "--final", "--out-dir", "--result"):
        b.add_argument(k, required=True)
    b.add_argument("--dossier"); b.add_argument("--script"); b.add_argument("--license-map")
    a = ap.parse_args()
    return cmd_build(a)


if __name__ == "__main__":
    sys.exit(main())
