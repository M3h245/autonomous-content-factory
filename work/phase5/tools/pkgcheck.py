"""Authoring aid: preview package_engine's deterministic thumbnail/copy checks + dHash diversity (no gate, no state)."""
import json, sys
from pathlib import Path
R = Path(__file__).resolve().parents[3] / "skills"
for p in ("content-factory/scripts", "video-quality-assurance/scripts", "video-production/scripts"):
    sys.path.insert(0, str(R / p))
import package_engine as pe
run, out = Path(sys.argv[1]), Path(sys.argv[2])
v = run / "videos" / "v01"
pol = json.loads((R / "video-quality-assurance/references/review-policy.json").read_text())["packaging"]
cpath = v / "package" / "package_candidates.json"
doc = json.loads(cpath.read_text())
from cf_common import validate as _validate
print("schema:", _validate(doc, "package_candidates") if "validate_artifact" not in dir(pe) else pe.validate_artifact(doc, "package_candidates"))
cands = doc["candidates"]
tm = json.loads((v / "audio" / "timing.json").read_text()); script = json.loads((v / "script" / "script.json").read_text())
facts = {f["id"]: f for f in json.loads((run / "research" / "dossier.json").read_text())["facts"]}
tr = {"text": " ".join(s["text"] for s in tm["sentences"]), "duration_s": tm.get("duration_s"),
      "sentences": [{"text": s["text"], "start": s["start"], "end": s["end"]} for s in tm["sentences"]]}
on = " ".join(b.get("on_screen", "") for b in script.get("beats", []))
pal = ["#ffd23f", "#e8452c", "#3b82c4", "#2f9e44", "#f783ac"]
meas = {}
for c in cands:
    cited = [facts[i] for i in c["claim_ids"] + c["thumbnail"].get("depicts", []) if i in facts]
    d = out / c["id"]; d.mkdir(parents=True, exist_ok=True)
    meas[c["id"]] = m = pe.render_thumb((cpath.parent / c["thumbnail"]["svg"]).resolve(), pal, d, pol)
    ch = pe.thumb_checks(c, m, pol, cited, set(facts), set(pe.words_of(tr["text"] + " " + on))) + pe.copy_checks(c, pol, cited, set(facts), tr, script.get("cta") or {})
    bad = [f'{x["id"]}: {x.get("evidence", "")}'[:160] for x in ch if x["severity"] in ("blocking", "major")]
    print(c["id"], "OK" if not bad else bad, "| subj", m["subject_core_height"], "second", m["second_subject_ratio"], "dead", m["dead_cells"])
issues, div = pe.diversity(cands, meas, pol)
print("near-duplicates:", issues)
