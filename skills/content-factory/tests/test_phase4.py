"""Phase 4: packaging — title/claim gates, misleading-claim fixtures, thumbnail readability/geometry, package diversity,
independent package reviewer, metadata regression and an end-to-end PACKAGE run with replay determinism.

    python -m unittest discover -s content-factory/tests -p "test_phase4.py" -v                   (~2-3 min)

The end-to-end class needs a finished run (default: the Phase 3.5 knuckle run copy, override with CF_PACKAGE_RUN).
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in ("content-factory/scripts", "video-quality-assurance/scripts", "asset-provenance/scripts"):
    sys.path.insert(0, str(ROOT / p))
import package_engine as PE  # noqa: E402
import media_clean as MC  # noqa: E402

POL_ALL = json.loads((ROOT / "video-quality-assurance" / "references" / "review-policy.json").read_text(encoding="utf-8"))
POL = POL_ALL["packaging"]
PALETTE = ["#ffd23f", "#e8452c", "#3b82c4", "#2f9e44", "#f783ac"]
SENTS = ["What actually pops when you crack your knuckles?", "Not your bones.", "Your joints sit in a capsule of fluid.",
         "Pull the joint apart, the pressure drops, and a gas cavity snaps open.", "In 2015, scientists filmed it inside an MRI.",
         "The pop happened as the bubble formed.", "A 2018 model says a partial collapse could still make the sound.",
         "The debate isn't over.", "And arthritis?", "A study of 215 people found no link.", "So it's just a bubble.", "Do you crack yours?"]
FACTS = [{"id": "f1", "claim": "The crack happens when the joint surfaces pull apart and a gas cavity suddenly forms in the joint fluid.", "source_ids": ["s1"], "risk": "low"},
         {"id": "f2", "claim": "Researchers filmed finger joints being pulled inside an MRI scanner in real time to watch the crack happen.", "source_ids": ["s1"], "risk": "low"},
         {"id": "f5", "claim": "A 2011 study of 215 people found no link between habitual knuckle cracking and hand osteoarthritis.", "source_ids": ["s3"], "risk": "medium"},
         {"id": "f6", "claim": "A doctor cracked the knuckles of only his left hand for 60 years, saw no arthritis difference between hands, and won the 2009 Ig Nobel Prize in Medicine.", "source_ids": ["s4"], "risk": "low"},
         {"id": "f7", "claim": "The gas cavity stays in the joint after the crack.", "source_ids": ["s1"], "risk": "low"}]
IDS = {f["id"] for f in FACTS}
CTA = {"needed": True, "decision_reason": "x", "type": "comment", "placement": "integrated", "modality": "both",
       "spoken": "Do you crack yours?", "on_screen": "DO YOU CRACK YOURS?"}


def transcript():
    out, t = [], 0.1
    for s in SENTS:
        d = 0.38 * len(s.split())
        out.append({"text": s, "start": round(t, 2), "end": round(t + d, 2)})
        t += d + 0.2
    return {"text": " ".join(SENTS), "duration_s": round(t, 2), "sentences": out}


TR = transcript()
SPOKEN = set(PE.words_of(TR["text"]))
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">'
SKIN = "#f6c9a8"


def fist(cx=560, base=1495, s=1.08):
    pw, fw = 170 * s, 85 * s
    o = f'<g id="fist" data-in="none"><rect x="{cx - pw}" y="{base - 420 * s}" width="{2 * pw}" height="{420 * s}" rx="{60 * s}" fill="{SKIN}"/>'
    for k in range(4):
        o += f'<rect x="{cx - pw + k * fw}" y="{base - 700 * s}" width="{fw}" height="{330 * s}" rx="{40 * s}" fill="{SKIN}"/>'
    o += (f'<rect x="{cx - pw - 70 * s}" y="{base - 380 * s}" width="{110 * s}" height="{230 * s}" rx="{50 * s}" fill="{SKIN}" '
          f'transform="rotate(-25 {cx - pw} {base - 260 * s})"/>')
    return o + "</g>"


def text(t, y=570, size=170, fill="#1d1b1a"):
    return f'<text x="540" y="{y}" font-family="marker" font-size="{size}" fill="{fill}" data-in="none">{t}</text>'


BURST = '<g data-lib="burst" data-r="94" data-n="8" data-fill="p0" transform="translate(800 900)" data-in="none"/>'
GOOD_SVG = SVG + fist() + BURST + text("NOT BONES") + "</svg>"


def cand(cid="P1", strategy="curiosity", title="What actually pops when you crack your knuckles?", thumb="NOT BONES",
         promise="That pop isn't your bones. Here's what an MRI saw.", svg="svg/P1.svg", depicts=("f1",), claim_ids=("f1", "f2"),
         desc="Scientists filmed a knuckle cracking inside an MRI: the joint pulls apart and a gas cavity forms in the fluid.",
         tags=("#science", "#humanbody", "#knucklecracking"), caption_cta="Do you crack yours?"):
    return {"id": cid, "strategy": strategy, "title": title, "opening_promise": promise,
            "thumbnail": {"concept": "c", "text": thumb, "svg": svg, "depicts": list(depicts)}, "description": desc,
            "hashtags": list(tags), "claim_ids": list(claim_ids), "caption_cta": caption_cta}


def cited(c):
    return [f for f in FACTS if f["id"] in set(c["claim_ids"]) | set(c["thumbnail"]["depicts"])]


def ids_of(checks):
    return {x["id"] for x in checks}


def render(svg_text):
    d = Path(tempfile.mkdtemp(prefix="p4thumb_"))
    (d / "t.svg").write_text(svg_text, encoding="utf-8")
    return PE.render_thumb(d / "t.svg", PALETTE, d, POL), d


# ============================================================================= titles + claims
class TitleValidation(unittest.TestCase):
    def check(self, **kw):
        c = cand(**kw)
        return ids_of(PE.copy_checks(c, POL, cited(c), IDS, TR, CTA))

    def test_good_title_passes(self):
        self.assertEqual(self.check(), set())

    def test_too_long_for_mobile(self):
        self.assertIn("TITLE.LENGTH", self.check(title="What actually pops inside the joint when you crack your knuckles every day"))

    def test_shouting_and_bait(self):
        got = self.check(title="SHOCKING: what REALLY pops in knuckles!!")
        self.assertTrue({"CLICKBAIT.PHRASE", "CLICKBAIT.CAPS", "CLICKBAIT.EXCLAMATION"} <= got, got)

    def test_off_topic_title_is_blocking(self):
        c = cand(title="Why cats purr when they are happy")
        res = PE.copy_checks(c, POL, cited(c), IDS, TR, CTA)
        self.assertIn(("TITLE.OFF_TOPIC", "blocking"), {(x["id"], x["severity"]) for x in res})

    def test_title_promising_what_the_video_never_says(self):
        self.assertIn("TITLE.NOT_IN_VIDEO", self.check(title="He cracked one hand for 60 years to test it", claim_ids=("f6",)))

    def test_opening_promise_must_match_the_videos_opening(self):
        self.assertIn("PROMISE.MATCHES_HOOK", self.check(promise="Pull a joint apart and the fluid inside does something odd."))

    def test_caption_cta_cannot_ask_for_something_else(self):
        got = self.check(caption_cta="Follow for part 2!")
        self.assertIn("CTA.PKG_CONFLICT", got)

    def test_unknown_fact_ids_block(self):
        self.assertIn("CLAIM.UNKNOWN_FACT", self.check(claim_ids=("f1", "f99")))

    def test_bad_hashtags(self):
        self.assertIn("TAGS.FORMAT", self.check(tags=("science",)))
        self.assertIn("TAGS.RELEVANT", self.check(tags=("#cooking", "#travel")))


class MisleadingClaims(unittest.TestCase):
    """Fixtures for claims the evidence does not support. Each must be blocking."""
    F5 = [FACTS[2]]

    def blocking(self, text, cited_facts=None):
        return {x["id"] for x in PE.claim_check(text, cited_facts if cited_facts is not None else self.F5, "title")
                if x["severity"] == "blocking"}

    def test_reversed_finding(self):
        got = self.blocking("Cracking your knuckles causes arthritis")
        self.assertTrue(got & {"CLAIM.UNSUPPORTED", "CLAIM.CONTRADICTS_EVIDENCE"}, got)

    def test_reversed_finding_with_supported_words(self):
        self.assertIn("CLAIM.CONTRADICTS_EVIDENCE", self.blocking("Knuckle cracking is linked to osteoarthritis"))

    def test_unsupported_number(self):
        self.assertIn("CLAIM.UNSUPPORTED_NUMBER", self.blocking("3 bubbles pop in every knuckle"))

    def test_unsupported_absolute(self):
        self.assertIn("CLAIM.UNSUPPORTED_ABSOLUTE", self.blocking("Science has proven knuckle cracking is harmless"))

    def test_unsupported_health_term(self):
        self.assertIn("CLAIM.UNSUPPORTED", self.blocking("Cracking your knuckles is bad for you"))

    def test_honest_question_is_allowed(self):
        self.assertEqual(self.blocking("Does cracking your knuckles cause arthritis?"), set())

    def test_negated_statement_matching_evidence_is_allowed(self):
        self.assertEqual(self.blocking("No link to arthritis: what 215 people showed"), set())

    def test_neutral_mention_is_not_an_assertion(self):
        self.assertEqual(self.blocking("What a study of 215 people found about arthritis"), set())

    def test_uncited_evidence_does_not_count(self):
        self.assertIn("CLAIM.UNSUPPORTED_NUMBER", self.blocking("215 people, no link", cited_facts=[FACTS[0]]))


# ============================================================================= thumbnails
class ThumbnailGeometry(unittest.TestCase):
    def checks(self, svg_text, thumb="NOT BONES", **kw):
        m, d = render(svg_text)
        c = cand(thumb=thumb, **kw)
        try:
            return ids_of(PE.thumb_checks(c, m, POL, cited(c), IDS, SPOKEN)), m
        finally:
            shutil.rmtree(d)

    def test_good_thumbnail_passes_and_reads_at_168(self):
        got, m = self.checks(GOOD_SVG)
        self.assertEqual(got, set(), m)
        self.assertGreaterEqual(min(t["height_168_px"] for t in m["texts"]), 20)
        self.assertGreater(m["texts"][0]["contrast_168"], 10)

    def test_tiny_text(self):
        got, _ = self.checks(SVG + fist() + text("NOT BONES", size=60) + "</svg>")
        self.assertTrue({"THUMB.TEXT_SIZE", "THUMB.HEADLINE_SIZE"} <= got, got)

    def test_too_many_words(self):
        got, _ = self.checks(SVG + fist() + text("NOT YOUR BONES AT ALL", size=96) + text("REALLY", y=700, size=120) + "</svg>",
                             thumb="NOT YOUR BONES AT ALL REALLY")
        self.assertIn("THUMB.WORDS", got)

    def test_low_contrast_text(self):
        got, _ = self.checks(SVG + fist() + text("NOT BONES", fill="#f3ead8") + "</svg>")
        self.assertIn("THUMB.CONTRAST", got)

    def test_text_outside_the_central_square(self):
        got, _ = self.checks(SVG + fist() + text("NOT BONES", y=250) + "</svg>")
        self.assertIn("THUMB.TEXT_CORE_SAFE", got)

    def test_small_subject_and_dead_space(self):
        got, _ = self.checks(SVG + fist(cx=300, base=1450, s=0.45) + text("NOT BONES") + "</svg>")
        self.assertTrue({"THUMB.SUBJECT", "THUMB.DEAD_SPACE"} <= got, got)

    def test_two_competing_subjects(self):
        two = SVG + fist(cx=300, base=1480, s=0.8).replace('id="fist"', 'id="a"') + \
            fist(cx=790, base=1480, s=0.8).replace('id="fist"', 'id="b"') + text("NOT BONES") + "</svg>"
        self.assertIn("THUMB.SINGLE_SUBJECT", self.checks(two)[0])

    def test_text_over_the_subject(self):
        got, _ = self.checks(SVG + fist(base=1495, s=1.45) + text("NOT BONES", y=600) + "</svg>")
        self.assertIn("THUMB.TEXT_OVERLAP", got)

    def test_clutter_of_tiny_details(self):
        dots = "".join(f'<circle cx="{120 + 110 * (k % 8)}" cy="{1380 + 40 * (k // 8)}" r="9" fill="#1d1b1a"/>' for k in range(16))
        got, _ = self.checks(SVG + fist(base=1300, s=0.9) + text("NOT BONES") + dots + "</svg>")
        self.assertIn("THUMB.CLUTTER", got)

    def test_declared_text_must_match_the_image(self):
        self.assertIn("THUMB.TEXT_MATCHES", self.checks(GOOD_SVG, thumb="GAS BUBBLE")[0])

    def test_false_visual_claim(self):
        got, _ = self.checks(SVG + fist() + text("60 YEARS") + "</svg>", thumb="60 YEARS", depicts=("f6",))
        self.assertIn("THUMB.NOT_IN_VIDEO", got)
        got, _ = self.checks(GOOD_SVG, depicts=("f42",))
        self.assertIn("THUMB.DEPICTS_KNOWN", got)

    def test_cta_on_thumbnail(self):
        got, _ = self.checks(SVG + fist() + text("COMMENT BELOW") + "</svg>", thumb="COMMENT BELOW")
        self.assertIn("THUMB.CTA", got)


# ============================================================================= end-to-end engine on a tiny fixture video
def make_fixture(tmp: Path, candidates: list, svgs: dict) -> dict:
    v = tmp / "v"
    (v / "package" / "svg").mkdir(parents=True)
    for k, s in svgs.items():
        (v / "package" / "svg" / f"{k}.svg").write_text(s, encoding="utf-8")
    (v / "package" / "package_candidates.json").write_text(json.dumps({"video_id": "v01", "language": "en", "candidates": candidates}), encoding="utf-8")
    script = {"video_id": "v01", "language": "en", "beats": [{"id": "b1", "role": "hook", "text": SENTS[0]}],
              "publish": {"title_options": ["x"], "description": "", "hashtags": []}, "cta": CTA}
    (tmp / "script.json").write_text(json.dumps(script), encoding="utf-8")
    (tmp / "timing.json").write_text(json.dumps({"language": "en", "duration_s": TR["duration_s"], "sentences": TR["sentences"], "words": []}), encoding="utf-8")
    (tmp / "dossier.json").write_text(json.dumps({"topic": "knuckles", "facts": FACTS, "sources": []}), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0xf4efe4:s=1080x1920:d=1", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(tmp / "final.mp4")], check=True)
    return {"cands": v / "package" / "package_candidates.json", "out": v / "package"}


def run_engine(tmp: Path, fx: dict, judgment: Path | None = None) -> tuple[int, dict]:
    cmd = [sys.executable, str(ROOT / "content-factory" / "scripts" / "package_engine.py"), "select", "--candidates", fx["cands"],
           "--script", tmp / "script.json", "--timing", tmp / "timing.json", "--final", tmp / "final.mp4",
           "--dossier", tmp / "dossier.json", "--out-dir", fx["out"]] + (["--judgment", judgment] if judgment else [])
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    return p.returncode, json.loads((fx["out"] / "package_selection.json").read_text(encoding="utf-8"))


THREE = ([cand(),
          cand("P2", "mechanism", "An MRI filmed a knuckle crack as it happened", "GAS BUBBLE",
               "What pops when a knuckle cracks? An MRI caught it happening.", "svg/P2.svg", ("f1", "f7"), ("f1", "f2")),
          cand("P3", "question", "Does cracking your knuckles cause arthritis?", "215 PEOPLE",
               "Cracking your knuckles: what actually pops, and is it hurting your joints?", "svg/P3.svg", ("f5",), ("f1", "f5"),
               desc="What pops when you crack your knuckles, and what a study of 215 people found about arthritis.")],
         {"P1": GOOD_SVG,
          "P2": SVG + '<g id="joint" data-in="none"><ellipse cx="540" cy="1107" rx="345" ry="225" fill="#cfe8ff"/>'
                '<rect x="345" y="720" width="390" height="320" rx="40" fill="#f3e6c8"/><rect x="345" y="1175" width="390" height="320" rx="40" fill="#f3e6c8"/></g>'
                '<circle cx="540" cy="1107" r="95" fill="white" stroke="p2" stroke-width="7" data-in="none"/>' + text("GAS BUBBLE", size=160) + "</svg>",
          "P3": SVG + fist(cx=450) + '<g data-lib="question" transform="translate(860 1050) scale(1.7)" data-in="none"/>' + text("215 PEOPLE", size=165) + "</svg>"})


class PackageDiversityAndSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p4eng_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_three_distinct_packages_select_one_with_reasons(self):
        fx = make_fixture(self.tmp, *copy.deepcopy(THREE))
        rc, sel = run_engine(self.tmp, fx)
        self.assertEqual(rc, 0, sel["set_checks"])
        self.assertEqual(sel["status"], "passed")
        self.assertEqual(len(sel["rejected"]), 2)
        self.assertTrue(all(r["reasons"] for r in sel["rejected"]))
        self.assertIsNotNone(sel["diversity"]["distinct_viable_set"])
        # selection = highest total among PASS candidates
        best = max((r for r in sel["table"] if r["passed"]), key=lambda r: r["total"])
        self.assertEqual(sel["selected"]["total"], best["total"])

    def test_superficial_variations_fail_diversity(self):
        c, s = copy.deepcopy(THREE)
        c[1] = cand("P2", "question", "What really pops when you crack your knuckles?", "NOT BONES", svg="svg/P2.svg")
        c[2] = cand("P3", "challenge", "What actually pops when you crack knuckles?", "NOT BONES", svg="svg/P3.svg")
        fx = make_fixture(self.tmp, c, {"P1": GOOD_SVG, "P2": GOOD_SVG, "P3": GOOD_SVG})
        rc, sel = run_engine(self.tmp, fx)
        self.assertEqual(rc, 2)
        self.assertIn("PKG.DIVERSITY", {s_["id"] for s_ in sel["set_checks"]})

    def test_extra_near_duplicate_is_rejected_not_fatal(self):
        c, s = copy.deepcopy(THREE)
        c.append(cand("P4", "story", "What pops in your knuckles, really?", "NOT BONES", svg="svg/P4.svg"))
        s["P4"] = GOOD_SVG
        fx = make_fixture(self.tmp, c, s)
        rc, sel = run_engine(self.tmp, fx)
        self.assertEqual(rc, 0, sel["set_checks"])
        self.assertNotEqual(sel["selected"]["id"], "P4")

    def test_only_misleading_alternatives_fail_the_set(self):
        c, s = copy.deepcopy(THREE)
        c[1]["title"] = "Cracking your knuckles causes arthritis"
        c[2]["title"] = "Doctors hate this: 3 bubbles in every knuckle!!"
        fx = make_fixture(self.tmp, c, s)
        rc, sel = run_engine(self.tmp, fx)
        self.assertEqual(rc, 2)
        self.assertIn("PKG.VIABLE", {s_["id"] for s_ in sel["set_checks"]})
        bad = {r["id"]: r for r in sel["table"]}
        self.assertFalse(bad["P2"]["passed"])
        self.assertEqual(bad["P2"]["scores"]["accuracy"], 1)

    def test_replay_is_deterministic(self):
        fx = make_fixture(self.tmp, *copy.deepcopy(THREE))
        _, a = run_engine(self.tmp, fx)
        h1 = {c: (fx["out"] / "candidates" / c / "thumbnail.jpg").read_bytes() for c in ("P1", "P2", "P3")}
        _, b = run_engine(self.tmp, fx)
        h2 = {c: (fx["out"] / "candidates" / c / "thumbnail.jpg").read_bytes() for c in ("P1", "P2", "P3")}
        self.assertEqual(h1, h2)
        self.assertEqual(json.dumps(a["table"], sort_keys=True), json.dumps(b["table"], sort_keys=True))
        self.assertEqual(a["selected"]["id"], b["selected"]["id"])


# ============================================================================= reviewer
class PackageReviewer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="p4rev_"))
        cls.fx = make_fixture(cls.tmp, *copy.deepcopy(THREE))
        cls.rc, cls.sel = run_engine(cls.tmp, cls.fx)
        cls.rev = json.loads((cls.fx["out"] / "review" / "package_reviews.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_packets_carry_no_author_intent(self):
        for c in ("P1", "P2", "P3"):
            pk = self.fx["out"] / "review" / "packets" / c
            man = json.loads((pk / "manifest.json").read_text(encoding="utf-8"))
            names = " ".join(man["files"])
            self.assertNotIn(".svg", names)
            body = (pk / "text" / "package.json").read_text(encoding="utf-8")
            for k in ("strategy", "concept", "rationale", "svg"):
                self.assertNotIn(f'"{k}"', body)

    def test_reviewer_runs_in_its_own_process_without_authoring_modules(self):
        for r in self.rev["results"]:
            b = r["boundary"]
            self.assertEqual(b["authoring_modules_loaded"], [])
            self.assertNotEqual(b["process"]["pid"], os.getpid())
            self.assertEqual(b["refused"], [])
            self.assertTrue(any(f["name"] == "frames/thumbnail_168.png" for f in b["files_read"]))

    def test_all_nine_dimensions_scored_with_evidence(self):
        for r in self.rev["results"]:
            self.assertEqual(set(r["scores"]), set(POL_ALL["package_thresholds"]))
            for d, v in r["scores"].items():
                self.assertTrue(v["evidence"], d)
                if v["score"] < 4:
                    self.assertTrue(v["explanation"], d)

    def test_side_note_title_scores_lower_on_promise_payoff(self):
        s = {r["candidate"]: r["scores"] for r in self.rev["results"]}
        self.assertLess(s["P3"]["promise_payoff"]["score"], s["P1"]["promise_payoff"]["score"])

    def test_external_judgment_can_lower_but_not_raise(self):
        j = self.tmp / "judgment.json"
        j.write_text(json.dumps({"candidates": {
            "P1": {"scores": {"curiosity": 2, "accuracy": 5, "thumbnail_appeal": 4}, "notes": {"curiosity": "flat"}},
            "P2": {"scores": {"curiosity": 5, "thumbnail_appeal": 4}},
            "P3": {"scores": {"thumbnail_appeal": 4}}}}), encoding="utf-8")
        out = self.tmp / "rv2"
        pk = [str(self.fx["out"] / "review" / "packets" / c) for c in ("P1", "P2", "P3")]
        subprocess.run([sys.executable, str(ROOT / "video-quality-assurance" / "scripts" / "reviewer.py"), "review-package",
                        "--packets", *pk, "--out", str(out), "--judgment", str(j)], check=True, capture_output=True)
        res = {r["candidate"]: r for r in json.loads((out / "package_reviews.json").read_text(encoding="utf-8"))["results"]}
        self.assertEqual(res["P1"]["scores"]["curiosity"]["score"], 2)
        self.assertEqual(res["P1"]["verdict"], "FAIL")
        base = {r["candidate"]: r for r in self.rev["results"]}
        self.assertEqual(res["P2"]["scores"]["curiosity"]["score"], base["P2"]["scores"]["curiosity"]["score"])
        self.assertEqual(res["P1"]["judge"], "heuristic+external")

    def test_thumbnail_repeating_the_title_is_capped(self):
        tmp = Path(tempfile.mkdtemp(prefix="p4rep_"))
        try:
            c, s = copy.deepcopy(THREE)
            c[0]["thumbnail"]["text"] = "CRACK YOUR KNUCKLES"
            s["P1"] = SVG + fist() + text("CRACK YOUR KNUCKLES", size=110) + "</svg>"
            fx = make_fixture(tmp, c, s)
            run_engine(tmp, fx)
            rev = {r["candidate"]: r for r in json.loads((fx["out"] / "review" / "package_reviews.json").read_text(encoding="utf-8"))["results"]}
            self.assertLessEqual(rev["P1"]["scores"]["complementarity"]["score"], 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_packet_tampering_is_refused(self):
        pk = self.tmp / "tampered"
        shutil.copytree(self.fx["out"] / "review" / "packets" / "P1", pk)
        (pk / "text" / "package.json").write_text('{"title": "changed"}', encoding="utf-8")
        p = subprocess.run([sys.executable, str(ROOT / "video-quality-assurance" / "scripts" / "reviewer.py"), "review-package",
                            "--packets", str(pk), "--out", str(self.tmp / "rv3")], capture_output=True, text=True)
        self.assertIn("boundary_violation", p.stdout)


# ============================================================================= metadata regression
class ThumbnailMetadata(unittest.TestCase):
    def test_rendered_thumbnail_is_clean_after_lossless_clean(self):
        m, d = render(GOOD_SVG)
        try:
            from PIL import Image
            dirty = d / "dirty.jpg"
            im = Image.open(d / "thumbnail.jpg")
            exif = Image.Exif()
            exif[0x0131] = "doodle pipeline factory v2.0.0-alpha8"
            im.save(dirty, "JPEG", quality=92, exif=exif.tobytes(), comment=b"/home/claude/runs debug")
            self.assertFalse(MC.audit(dirty)["clean"])
            MC.clean(dirty, d / "clean.jpg")
            self.assertTrue(MC.audit(d / "clean.jpg")["clean"], MC.audit(d / "clean.jpg"))
            import numpy as np
            self.assertTrue((np.asarray(Image.open(dirty)) == np.asarray(Image.open(d / "clean.jpg"))).all())
        finally:
            shutil.rmtree(d)


# ============================================================================= PACKAGE stage end-to-end on a finished run
# repository layout: <repo>/skills/<skill>/... and <repo>/fixtures/phase4_package_run/<run> (portability, cloud handoff)
DEFAULT_RUN = ROOT.parent / "fixtures" / "phase4_package_run" / "2026-10-07-why-your-knuckles-crack"


class PackageStageEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = Path(os.environ.get("CF_PACKAGE_RUN", DEFAULT_RUN))
        if not (src / "videos" / "v01" / "package" / "package_candidates.json").exists():
            raise unittest.SkipTest(f"no finished run with package candidates at {src} (set CF_PACKAGE_RUN)")
        cls.tmp = Path(tempfile.mkdtemp(prefix="p4e2e_"))
        cls.rundir = cls.tmp / src.name
        shutil.copytree(src, cls.rundir, ignore=shutil.ignore_patterns("*.zip"))
        shutil.rmtree(cls.rundir / "package" / "v01", ignore_errors=True)
        cls.pkg = cls.rundir / "package" / "v01"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def package(self):
        p = subprocess.run([sys.executable, str(ROOT / "content-factory" / "scripts" / "package_run.py"), "--run", str(self.rundir),
                            "--video", "v01"], capture_output=True, text=True)
        return p.returncode, json.loads((self.pkg / "result.json").read_text(encoding="utf-8"))

    def test_1_package_passes_with_all_gates(self):
        rc, res = self.package()
        self.assertEqual(rc, 0, [c for c in res["gate"]["checks"] if not c["passed"]])
        got = {c["id"]: c["passed"] for c in res["gate"]["checks"]}
        for g in ("PKG.PACKAGING", "PKG.MEDIA_METADATA_CLEAN", "PKG.FINAL_DECODES", "PKG.DISCLOSURE", "PKG.PUBLIC_COPY_CLEAN",
                  "PKG.THUMBNAIL_DECODES", "PKG.FILES", "PKG.CHECKSUM"):
            self.assertTrue(got.get(g), g)
        meta = json.loads((self.pkg / "metadata.json").read_text(encoding="utf-8"))
        sel = json.loads((self.rundir / "videos" / "v01" / "package" / "package_selection.json").read_text(encoding="utf-8"))["selected"]
        self.assertEqual(meta["title"], sel["title"])
        self.assertEqual((self.pkg / "cover.jpg").read_bytes(), (self.pkg / "thumbnail.jpg").read_bytes())
        self.assertIn(meta["youtube"]["description"].split("\n")[0], sel["opening_promise"])
        pub = json.loads((self.pkg / "publishing_package.json").read_text(encoding="utf-8"))
        self.assertTrue(pub["internal"]["rejected"])
        self.assertNotIn(sel["id"], json.dumps(pub["public"]))
        for f in ("thumbnail.jpg", "cover.jpg", "thumbnail_crops.jpg", "final.mp4"):
            self.assertTrue(MC.audit(self.pkg / f)["clean"], f)

    def test_2_disclosure_and_metadata_policy_unchanged(self):
        meta = json.loads((self.pkg / "metadata.json").read_text(encoding="utf-8"))
        prov = json.loads((self.pkg / "provenance.json").read_text(encoding="utf-8"))
        self.assertNotIn(prov["disclosure"]["description_line"], meta["youtube"]["description"])   # v3.0.2: labels only
        self.assertEqual(meta["hashtags_copy_ready"], ", ".join(h.lstrip("#") for h in meta["hashtags"]))
        self.assertIsNotNone(meta["tiktok"]["ai_generated_label"])
        self.assertIsNotNone(meta["instagram"]["ai_info"])

    def test_3_dirty_media_in_the_package_fails(self):
        from PIL import Image
        import package_run as PR
        orig = MC.clean_jpg
        try:
            PR_media = sys.modules["media_clean"]
            # simulate a cleaner that silently leaves internal metadata behind
            PR_media.clean_jpg = lambda s, d: Image.open(s).save(d, "JPEG", comment=b"factory debug /home/claude")
            from cf_common import read_json  # noqa: F401
            res = PR.package_video(self.rundir, "v01", 9)
        finally:
            sys.modules["media_clean"].clean_jpg = orig
        got = {c["id"]: c for c in res["gate"]["checks"]}
        self.assertFalse(got["PKG.MEDIA_METADATA_CLEAN"]["passed"])
        self.assertEqual(res["status"], "failed")

    def test_4_brief_flag_without_candidates_blocks(self):
        run2 = self.tmp / "nocands"
        shutil.copytree(self.rundir, run2, ignore=shutil.ignore_patterns("*.zip"))
        (run2 / "videos" / "v01" / "package" / "package_candidates.json").unlink()
        b = json.loads((run2 / "run.json").read_text(encoding="utf-8"))
        b["package_engine"] = "v1"
        (run2 / "run.json").write_text(json.dumps(b), encoding="utf-8")
        p = subprocess.run([sys.executable, str(ROOT / "content-factory" / "scripts" / "package_run.py"), "--run", str(run2),
                            "--video", "v01"], capture_output=True, text=True)
        res = json.loads((run2 / "package" / "v01" / "result.json").read_text(encoding="utf-8"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("PKG.CANDIDATES", {c["id"] for c in res["gate"]["checks"] if not c["passed"]})

    def test_5_old_run_without_packaging_is_unchanged(self):
        run3 = self.tmp / "old"
        shutil.copytree(self.rundir, run3, ignore=shutil.ignore_patterns("*.zip"))
        shutil.rmtree(run3 / "videos" / "v01" / "package")
        shutil.rmtree(run3 / "package" / "v01", ignore_errors=True)
        p = subprocess.run([sys.executable, str(ROOT / "content-factory" / "scripts" / "package_run.py"), "--run", str(run3),
                            "--video", "v01"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout[-500:])
        self.assertFalse((run3 / "package" / "v01" / "thumbnail.jpg").exists())
        meta = json.loads((run3 / "package" / "v01" / "metadata.json").read_text(encoding="utf-8"))
        script = json.loads((run3 / "videos" / "v01" / "script" / "script.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["title"], script["publish"]["title_options"][0])


# ============================================================================= regression found by the Phase 4 fresh run
class SubtitleCommaChunk(unittest.TestCase):
    def test_short_comma_word_is_not_left_alone(self):
        sys.path.insert(0, str(ROOT / "subtitle-production" / "scripts"))
        import argparse
        import subtitles as SUB
        words = [{"w": w, "start": s, "end": e, "sentence": 0} for w, s, e in
                 (("So,", 30.961, 31.086), ("do", 31.136, 31.236), ("you", 31.261, 31.336), ("sip", 31.411, 31.611),
                  ("or", 31.636, 31.711), ("gulp?", 31.761, 32.118))]
        tm = {"language": "en", "duration_s": 32.6, "words": words, "sentences": [{"i": 0, "text": "So, do you sip or gulp?",
                                                                                  "start": 30.961, "end": 32.118}]}
        for mw in (3, 4, 5):
            a = argparse.Namespace(style="doodle", font="Permanent Marker", case="upper", max_words=mw, y=0.63, font_scale=1.0,
                                   overlays=None, crf=18, preset="medium")
            _, chunks, _ = SUB.build_ass(tm, a, [])
            self.assertFalse([c for c, s in chunks if s[1] - s[0] < 0.25], (mw, [[w["w"] for w in c] for c, _ in chunks]))
        # a comma with enough time on screen still breaks the line
        words2 = [dict(w) for w in words]
        words2[1]["start"], words2[1]["end"] = 31.5, 31.6
        tm["words"] = words2
        _, chunks, _ = SUB.build_ass(tm, argparse.Namespace(style="doodle", font="Permanent Marker", case="upper", max_words=3,
                                                            y=0.63, font_scale=1.0, overlays=None, crf=18, preset="medium"), [])
        self.assertEqual([w["w"] for w in chunks[0][0]], ["So,"])


if __name__ == "__main__":
    unittest.main()
