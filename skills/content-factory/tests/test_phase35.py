"""Phase 3.5: CTA gates (good + deliberately bad CTAs), reviewer CTA dimensions, final-media metadata policy.

    python -m unittest discover -s content-factory/tests -p "test_phase35.py" -v          (~15 s)
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in ("short-form-script/scripts", "video-quality-assurance/scripts", "asset-provenance/scripts"):
    sys.path.insert(0, str(ROOT / p))
import cta as CTA  # noqa: E402
import media_clean as MC  # noqa: E402
import reviewer as R  # noqa: E402

TOPIC = "Why your knuckles crack"


def beat(i, role, text):
    return {"id": i, "role": role, "text": text, "claim_ids": []}


def timeline(beats, t0=0.1, per_word=0.36, gap=0.25):
    """Deterministic fake timeline: one sentence per beat text sentence, 0.36 s per word."""
    out, t = [], t0
    for b in beats:
        for sent in [x.strip() for x in b["text"].replace("? ", "?|").replace(". ", ".|").split("|") if x.strip()]:
            d = per_word * len(sent.split())
            out.append({"text": sent, "beat_id": b["id"], "start": round(t, 3), "end": round(t + d, 3)})
            t += d + 0.16
        t += gap
    return out, t + 0.4


BASE = [beat("b1", "hook", "That knuckle crack? It's a bubble, not a bone."),
        beat("b2", "value", "Pulling the joint apart drops the pressure in its fluid."),
        beat("b3", "value", "A gas cavity snaps open, and that is the pop you hear."),
        beat("b4", "value", "Scientists filmed it inside an MRI scanner in 2015."),
        beat("b5", "payoff", "So the sound is the bubble forming, not bones grinding."),
        beat("b6", "loop", "Next time you crack them, you're making a bubble.")]


def good_cta():
    beats = copy.deepcopy(BASE)
    beats[5] = beat("b6", "loop", "Next time you crack them, you're making a bubble. Do you crack yours?")
    cta = {"needed": True, "decision_reason": "invites a personal answer", "type": "comment", "placement": "integrated",
           "modality": "both", "beat_id": "b6", "spoken": "Do you crack yours?", "on_screen": "Do you crack yours?"}
    return {"beats": beats, "cta": cta}


def run(script, history=None, labels=None):
    sents, dur = timeline(script["beats"])
    r = CTA.check(script, sents, dur, history=history, topic=TOPIC, labels=labels, title="Why knuckles crack")
    return {c["id"]: c for c in r["checks"]}, r


def failed(checks):
    return {k for k, c in checks.items() if not c["passed"]}


class CtaGates(unittest.TestCase):
    def test_good_integrated_comment_cta_passes(self):
        ck, r = run(good_cta())
        self.assertEqual(failed(ck), set(), {k: ck[k]["evidence"] for k in failed(ck)})
        self.assertGreater(r["window"][0], 0)

    def test_no_cta_decision_is_valid(self):
        s = {"beats": copy.deepcopy(BASE), "cta": {"needed": False, "decision_reason": "loop ending carries the video"}}
        ck, r = run(s)
        self.assertEqual(failed(ck), set())
        self.assertEqual(r["metrics"]["decision_reason"], "loop ending carries the video")

    # ---- deliberately bad CTAs: each must fail for its own reason
    def test_bad_cta_in_hook(self):
        s = good_cta()
        s["beats"][0] = beat("b1", "hook", "Follow for knuckle facts. That crack is a bubble, not a bone.")
        s["cta"].update(type="follow", beat_id="b1", spoken="Follow for knuckle facts.", modality="spoken", on_screen="")
        self.assertIn("CTA.NOT_IN_HOOK", failed(run(s)[0]))

    def test_bad_cta_interrupts_payoff(self):
        s = good_cta()
        s["beats"][4] = beat("b5", "payoff", "Save this for later. So the sound is the bubble forming, not bones grinding.")
        s["cta"].update(type="save", beat_id="b5", spoken="Save this for later.", modality="spoken", on_screen="")
        self.assertIn("CTA.AFTER_PAYOFF", failed(run(s)[0]))

    def test_bad_cta_too_long(self):
        s = good_cta()
        long = "Tell me in the comments whether you crack your knuckles every single morning or only when you are stressed out."
        s["beats"][5] = beat("b6", "loop", "Next time you crack them, you're making a bubble. " + long)
        s["cta"].update(spoken=long, modality="spoken", on_screen="")
        self.assertIn("CTA.DURATION", failed(run(s)[0]))

    def test_bad_cta_after_loop_breaks_ending(self):
        s = good_cta()
        s["beats"][5] = copy.deepcopy(BASE[5])
        s["beats"].append(beat("b7", "cta", "Follow for more knuckle bubble facts."))
        s["cta"].update(type="follow", placement="after_payoff", beat_id="b7", spoken="Follow for more knuckle bubble facts.",
                        modality="spoken", on_screen="")
        self.assertIn("CTA.ENDING", failed(run(s)[0]))

    def test_bad_cta_generic_outro(self):
        s = good_cta()
        s["beats"][5] = beat("b6", "loop", "Next time you crack them, you're making a bubble. Like and subscribe!")
        s["cta"].update(type="subscribe", spoken="Like and subscribe!", modality="spoken", on_screen="")
        ck = run(s)[0]
        self.assertIn("CTA.RELEVANCE", failed(ck))

    def test_bad_cta_repeated_from_history(self):
        ck = run(good_cta(), history=["Do you crack yours? Do you crack yours?"])[0]
        self.assertIn("CTA.NOT_REPEATED", failed(ck))

    def test_bad_undeclared_second_cta(self):
        s = good_cta()
        s["beats"][2] = beat("b3", "value", "A gas cavity snaps open. Share this with a friend who cracks theirs.")
        self.assertIn("CTA.SINGLE", failed(run(s)[0]))

    def test_bad_ending_only_works_with_cta(self):
        s = good_cta()
        s["beats"] = s["beats"][:4] + [beat("b5", "payoff", "So the sound is the bubble forming."),
                                       beat("b6", "cta", "Comment if you crack yours.")]
        s["cta"].update(placement="after_payoff", beat_id="b6", spoken="Comment if you crack yours.", modality="spoken", on_screen="")
        ck = run(s)[0]
        self.assertTrue(ck["CTA.STANDALONE_ENDING"]["passed"])      # payoff remains as the last content beat → fine
        s["beats"][4]["role"] = "value"                              # …but without a payoff the video only ends on the CTA
        self.assertTrue({"CTA.STANDALONE_ENDING", "CTA.AFTER_PAYOFF"} & failed(run(s)[0]))

    def test_bad_schema(self):
        s = good_cta()
        s["cta"].update(spoken="This sentence is not in the beat.")
        self.assertIn("CTA.SCHEMA", failed(run(s)[0]))

    def test_on_screen_cta_must_really_show(self):
        s = good_cta()
        sents, dur = timeline(s["beats"])
        r = CTA.check(s, sents, dur, labels=[], topic=TOPIC)
        self.assertIn("CTA.ON_SCREEN_SHOWN", {c["id"] for c in r["checks"] if not c["passed"]})
        lab = [{"text": "Do you crack yours?", "at_s": r["window"][0]}]
        r = CTA.check(s, sents, dur, labels=lab, topic=TOPIC)
        self.assertNotIn("CTA.ON_SCREEN_SHOWN", {c["id"] for c in r["checks"] if not c["passed"]})


class ReviewerCta(unittest.TestCase):
    def pub(self, s, r):
        c = s["cta"]
        return {"present": True, "type": c["type"], "placement": c["placement"], "modality": c["modality"],
                "spoken": c.get("spoken", ""), "on_screen": c.get("on_screen", ""), "window_s": r["window"]}

    def test_good_cta_scores_strong(self):
        s = good_cta()
        ck, r = run(s)
        sc = R.cta_scores(self.pub(s, r), r["checks"], " ".join(b["text"] for b in s["beats"]), timeline(s["beats"])[1], "Why knuckles crack")
        self.assertEqual(set(sc), set(R.CTA_DIMS))
        for d, v in sc.items():
            self.assertGreaterEqual(v["score"], 4, (d, v["evidence"]))

    def test_bad_cta_scores_low_with_reasons(self):
        s = good_cta()
        s["beats"][5] = beat("b6", "loop", "Next time you crack them, you're making a bubble. Smash that like button and subscribe!")
        s["cta"].update(type="like", spoken="Smash that like button and subscribe!", modality="spoken", on_screen="")
        ck, r = run(s)
        sc = R.cta_scores(self.pub(s, r), r["checks"], " ".join(b["text"] for b in s["beats"]), timeline(s["beats"])[1], "Why knuckles crack")
        self.assertLessEqual(sc["cta_quality"]["score"], 2)
        self.assertLessEqual(sc["cta_relevance"]["score"], 2)
        for d in ("cta_quality", "cta_relevance"):
            self.assertTrue(sc[d]["explanation"])

    def test_no_cta_means_no_cta_dims(self):
        self.assertEqual(R.cta_scores({"present": False}, [], "x", 30), {})

    def test_policy_fails_weak_cta_dims(self):
        pol = json.load(open(R.DEFAULT_POLICY))
        ok = {d: {"score": 4, "explanation": "", "evidence": ["e"]} for d in R.DIMS}
        weak = {**ok, "cta_relevance": {"score": 2, "explanation": "generic", "evidence": ["e"]}}
        verdict, fails = R.decide(weak, [], pol)
        self.assertEqual(verdict, "FAIL")
        self.assertEqual(fails[0]["fix_route"]["action"], "revise_cta")
        self.assertEqual(R.decide(ok, [], pol)[0], "PASS")                  # no CTA dims → not applied


class StemRegression(unittest.TestCase):
    def test_short_plurals_match(self):
        """Regression (Phase 3.5 run): 'what pops?' answered by 'the pop happened' was scored as never addressed."""
        self.assertEqual(R.stem("pops"), R.stem("pop"))
        self.assertEqual(R.stem("wrinkled"), R.stem("wrinkle"))
        self.assertEqual(R.stem("glass"), "glass")
        self.assertEqual(R.stem("gas"), "gas")


class MediaMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = Path(tempfile.mkdtemp(prefix="p35m_"))
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=320x568:d=1:r=25", "-f", "lavfi", "-i",
                        "sine=f=300:d=1:sample_rate=48000", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                        "-metadata", "comment=cf-provenance run-video=v01 /home/claude/runs/x checkpoint v2.0.0-alpha7",
                        str(cls.d / "dirty.mp4")], check=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(cls.d / "dirty.mp4"), "-frames:v", "1", "-q:v", "2",
                        str(cls.d / "dirty.jpg")], check=True)

    def test_audit_catches_internal_metadata(self):
        a = MC.audit(self.d / "dirty.mp4")
        vals = " ".join(f["value"] for f in a["findings"])
        self.assertFalse(a["clean"])
        for needle in ("cf-provenance", "Lavf", "x264 - core", "/home/"):
            self.assertIn(needle.lower(), vals.lower())
        self.assertFalse(MC.audit(self.d / "dirty.jpg")["clean"])       # ffmpeg writes a Lavc comment into JPEGs

    def test_clean_jpeg_is_lossless_and_clean(self):
        from PIL import Image, ImageChops
        MC.clean(self.d / "dirty.jpg", self.d / "c.jpg")
        self.assertTrue(MC.audit(self.d / "c.jpg")["clean"], MC.audit(self.d / "c.jpg"))
        a, b = Image.open(self.d / "dirty.jpg").convert("RGB"), Image.open(self.d / "c.jpg").convert("RGB")
        self.assertIsNone(ImageChops.difference(a, b).getbbox())

    def test_clean_mp4_keeps_streams_and_removes_container_metadata(self):
        MC.clean(self.d / "dirty.mp4", self.d / "c.mp4")
        md5 = lambda f, s: subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-map", f"0:{s}", "-f", "md5", "-"],  # noqa: E731
                                          capture_output=True, text=True).stdout
        self.assertEqual(md5(self.d / "dirty.mp4", "v"), md5(self.d / "c.mp4", "v"))
        self.assertEqual(md5(self.d / "dirty.mp4", "a"), md5(self.d / "c.mp4", "a"))
        left = {f["value"] for f in MC.audit(self.d / "c.mp4")["findings"]}
        self.assertTrue(all(v.lower().startswith("lav") for v in left), left)   # only the AAC encoder string can remain…

    def test_bitexact_audio_leaves_nothing(self):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(self.d / "dirty.mp4"), "-c:v", "copy", "-c:a", "aac",
                        "-flags:a", "+bitexact", str(self.d / "be.mp4")], check=True)
        MC.clean(self.d / "be.mp4", self.d / "be_c.mp4")
        self.assertTrue(MC.audit(self.d / "be_c.mp4")["clean"], MC.audit(self.d / "be_c.mp4"))   # …and +bitexact removes it

    def test_render_video_encodes_audio_bitexact(self):
        src = (ROOT / "video-production/scripts/render_video.py").read_text()
        self.assertIn('"-flags:a", "+bitexact"', src)
        prov = (ROOT / "asset-provenance/scripts/provenance.py").read_text()
        self.assertNotIn('"-metadata", f"comment=', prov)


if __name__ == "__main__":
    unittest.main()
