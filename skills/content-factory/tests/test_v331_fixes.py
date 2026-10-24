"""v3.3.1 regressions found on 2026-10-22/23 (goosebumps run and the first two channel-CTA videos)."""
import json, sys, tempfile, unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[2]
for d in ("short-form-script/scripts", "hook-engineering/scripts", "video-quality-assurance/scripts"):
    sys.path.insert(0, str(SK / d))
import cta as CTA  # noqa: E402


def script(last):
    return {"beats": [{"id": "b1", "role": "hook", "text": "Why do your ears pop on a plane?"},
                      {"id": "b2", "role": "payoff", "text": "When the tube opens, a bubble of air slips through."},
                      {"id": "b3", "role": "loop", "text": last}]}


def sents(sc):
    t, out = 0.0, []
    for b in sc["beats"]:
        for s in b["text"].replace("?", "?.").split(". "):
            s = s.strip(" .")
            if s:
                out.append({"beat_id": b["id"], "text": s, "start": t, "end": t + 1.4}); t += 1.5
    return out


class ChannelCta(unittest.TestCase):
    def test_channel_line_is_exempt_from_relevance_and_repeat(self):
        sc = script("Follow for a daily mystery. And that pop? Just one bubble.")
        sc["cta"] = {"needed": True, "decision_reason": "channel line", "type": "follow", "placement": "integrated",
                     "modality": "both", "beat_id": "b3", **CTA.CHANNEL_CTA}
        hist = [CTA.CHANNEL_CTA["spoken"] + " " + CTA.CHANNEL_CTA["on_screen"]] * 3
        res = CTA.check(sc, sents(sc), 22.0, history=hist)
        ck = {c["id"]: c["passed"] for c in res["checks"]}
        self.assertTrue(ck["CTA.RELEVANCE"]); self.assertTrue(ck["CTA.NOT_REPEATED"]); self.assertTrue(res["metrics"]["channel_cta"])

    def test_other_ctas_still_need_relevance_and_novelty(self):
        sc = script("Follow for daily science facts. And that pop? Just one bubble.")
        sc["cta"] = {"needed": True, "decision_reason": "x", "type": "follow", "placement": "integrated", "modality": "both",
                     "beat_id": "b3", "spoken": "Follow for daily science facts.", "on_screen": "FOLLOW FOR SCIENCE"}
        res = CTA.check(sc, sents(sc), 22.0, history=["Follow for daily science facts. FOLLOW FOR SCIENCE"])
        ck = {c["id"]: c["passed"] for c in res["checks"]}
        self.assertFalse(ck["CTA.RELEVANCE"]); self.assertFalse(ck["CTA.NOT_REPEATED"])


class HookIdeaMatch(unittest.TestCase):
    def test_selected_idea_facts(self):
        import hook_engine as H
        with tempfile.TemporaryDirectory() as t:
            s, i = Path(t, "sel.json"), Path(t, "ideas.json")
            s.write_text(json.dumps({"selected": [{"video_id": "v01", "idea_id": "idea-vestigial"}]}))
            i.write_text(json.dumps({"ideas": [{"id": "idea-vestigial", "fact_ids": ["F1", "F2", "F3", "F5"]},
                                               {"id": "idea-music", "fact_ids": ["F6", "F7"]}]}))
            facts = H.idea_fact_ids(str(s), str(i), "v01")
            self.assertEqual(facts, {"F1", "F2", "F3", "F5"})
            # the goosebumps hook h3 promised F6/F7: off the selected idea
            self.assertFalse({"F6", "F7"} & facts)
            self.assertEqual(H.idea_fact_ids(None, None, "v01"), set())


class TitleOnTopic(unittest.TestCase):
    def test_title_restating_topic_is_not_a_side_note(self):
        import reviewer as R
        W = set(R.words_of("Why does your foot fall asleep?")) - R.FUNC
        first = set(R.words_of("Here's what's really jammed inside a sleeping foot."))
        focus = W - first
        topic_w = set(R.words_of("Why does your foot fall asleep?")) - R.FUNC
        self.assertTrue(focus and focus <= topic_w)


class DrawingLibrary(unittest.TestCase):
    def test_every_part_expands_and_renders(self):
        sys.path.insert(0, str(SK / "video-production/scripts"))
        import doodle_lib as L
        import doodle_parts as P
        for name in P.PARTS:
            self.assertIn(name, L.COMPONENTS)
            self.assertTrue(L.expand(name, {}).strip().startswith("<"), name)
        import doodle_engine as DE
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">' + "".join(
            f'<g data-lib="{n}" transform="translate({200 + (i % 3) * 340} {300 + (i // 3) * 300}) scale(0.4)" data-in="none"/>'
            for i, n in enumerate(P.PARTS)) + "</svg>"
        DE.set_canvas(1080, 1920)
        sb = {"video_id": "t", "style": {"palette": ["#ffd23f", "#e8452c", "#3b82c4"], "paper": "plain"},
              "shots": [{"id": "s1", "start": 0.0, "visual": {"kind": "doodle", "svg": svg}, "camera": {"drift": "none"}}]}
        tl = DE.build_timeline(sb, {"duration_s": 1.0, "words": []})
        tl.duration = 1.0
        self.assertIsNotNone(tl.frame(0.5))


class VideoReviewDrawingQuality(unittest.TestCase):
    def test_judge_only_dimension_gates_nothing_without_a_judge(self):
        import reviewer as R
        self.assertIn("drawing_quality", R.DIMS)
        sc = {d: {"score": 4, "evidence": ["e"], "explanation": ""} for d in R.DIMS}
        sc["drawing_quality"] = {"score": 3, "evidence": ["e"], "explanation": "x", "not_judged": True}
        pol = {"thresholds": {"drawing_quality": 4}, "min_any_dimension": 3}
        verdict, fails = R.decide(sc, [], pol)
        self.assertEqual(verdict, "PASS")
        sc["drawing_quality"] = {"score": 3, "evidence": ["e"], "explanation": "foot drawn as a box"}
        verdict, fails = R.decide(sc, [], pol)
        self.assertEqual(verdict, "FAIL")


class HookFrame0Canvas(unittest.TestCase):
    def test_wide_hook_is_measured_on_its_own_canvas(self):
        sys.path.insert(0, str(SK / "video-production/scripts"))
        import hook_engine as HE
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080">'
               '<text x="960" y="150" font-family="marker" font-size="100" text-anchor="middle" data-in="none">NOT COLDER</text>'
               '<rect x="700" y="300" width="500" height="600" fill="#9a9a9a" data-in="none"/></svg>')
        with tempfile.TemporaryDirectory() as d:
            stats, _w = HE.render(svg, [{"w": "Not", "start": 0.0, "end": 0.4}], ["#ffd23f"], {"frame0": 0.0}, Path(d))
        t = stats["texts_t0"][0]
        self.assertEqual(t["lost_words"], []); self.assertTrue(t["inside_safe"])
        self.assertGreater(stats["subject_height_ratio"], 0.5)   # 600 px of 1080, not of 1920


class TwoLineFollowCard(unittest.TestCase):
    def test_follow_card_split_over_two_text_lines_counts_as_shown(self):
        sc = script("Follow for a daily mystery. And that pop? Just one bubble.")
        sc["cta"] = {"needed": True, "decision_reason": "channel line", "type": "follow", "placement": "integrated",
                     "modality": "both", "beat_id": "b3", **CTA.CHANNEL_CTA}
        ss = sents(sc)
        st = [x for x in ss if x["text"].startswith("Follow")][0]["start"]
        labels = [{"text": "FOLLOW", "at_s": st}, {"text": "BRAIN ACADEMY", "at_s": st}]
        res = CTA.check(sc, ss, 22.0, labels=labels)
        self.assertTrue({c["id"]: c["passed"] for c in res["checks"]}["CTA.ON_SCREEN_SHOWN"])


class WideDensity(unittest.TestCase):
    def test_interior_gap_on_16x9_gets_one_on_canvas_accent(self):
        sys.path.insert(0, str(SK / "video-production/scripts")); sys.path.insert(0, str(SK / "visual-storyboarding/scripts"))
        import doodle_engine as DE
        import density_events as D
        DE.set_canvas(1920, 1080)
        try:
            ws = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen".split()
            words = [{"w": w, "start": round(0.5 * i, 2), "end": round(0.5 * i + 0.4, 2)} for i, w in enumerate(ws)]
            svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080">'
                   '<text x="960" y="130" font-family="marker" font-size="84" text-anchor="middle" data-in="write" data-at="0">TITLE</text>'
                   '<rect x="560" y="300" width="800" height="450" fill="#9a9a9a" data-in="pop" data-at="w:two"/>'
                   '<circle cx="960" cy="520" r="120" fill="#e8452c" data-in="pop" data-at="w:fourteen"/></svg>')
            style = {"palette": ["#ffd23f"], "paper": "plain"}
            new, added = D.densify(svg, words, style, "t", 3.5)
            self.assertGreaterEqual(len(added), 1)
            for a in added:
                self.assertLess(a["anchor"][1], 864)                 # above the 16:9 caption band, on canvas
                self.assertGreater(a["at_s"], 1.0); self.assertLess(a["at_s"], 6.5)   # inside the interior gap
            times, _ = D.entrance_times(new, words, style, "t")
            self.assertLessEqual(max(b - a for a, b in zip(times, times[1:])), 3.5)
        finally:
            DE.set_canvas(1080, 1920)


class WideBurnProbe(unittest.TestCase):
    def test_caption_band_probe_reads_the_16x9_band(self):
        import shutil, subprocess
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg missing")
        sys.path.insert(0, str(SK / "subtitle-production/scripts"))
        import subtitles as SUB
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.mp4", Path(d) / "b.mp4"
            base = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=white:s=1920x1080:d=1", "-pix_fmt", "yuv420p"]
            subprocess.run(base + [str(a)], check=True)
            subprocess.run(base[:-2] + ["-vf", "drawbox=x=400:y=880:w=1100:h=100:color=black:t=fill", "-pix_fmt", "yuv420p", str(b)], check=True)
            SUB.set_canvas(1920, 1080)
            try:
                self.assertGreaterEqual(SUB.caption_band_diff(a, b, 0.5, 929), 40)
            finally:
                SUB.set_canvas(1080, 1920)


class CaptionPhraseBreaks(unittest.TestCase):
    def test_word_count_break_never_ends_on_a_function_word(self):
        sys.path.insert(0, str(SK / "subtitle-production/scripts"))
        import subtitles as SUB

        class W:
            def width(self, t):
                return len(t) * 20
        txt = "A metal spoon and a wooden spoon sat in a drawer all night".split()
        ws = [{"w": t, "start": i * 0.3, "end": i * 0.3 + 0.25, "sentence": 0} for i, t in enumerate(txt)]
        chunks = SUB.chunk_words(ws, 5, 10000, W(), lambda x: x)
        self.assertEqual(sum(len(c) for c in chunks), len(txt))
        for c in chunks[:-1]:
            self.assertNotIn(SUB._norm(c[-1]["w"]), SUB.WEAK_END)


class PacketHashIgnoresBuildTime(unittest.TestCase):
    def test_rebuilt_identical_packet_keeps_its_hash(self):
        import reviewer as RV
        with tempfile.TemporaryDirectory() as d:
            m = {"packet_version": 1, "built_at": "2026-10-24T13:44:23+00:00", "files": {"a.txt": {"sha256": "x", "bytes": 1}}}
            (Path(d) / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
            h1 = RV.Packet(Path(d)).manifest_sha
            m["built_at"] = "2026-10-24T13:44:35+00:00"
            (Path(d) / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
            self.assertEqual(RV.Packet(Path(d)).manifest_sha, h1)
            m["files"]["a.txt"]["sha256"] = "y"
            (Path(d) / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
            self.assertNotEqual(RV.Packet(Path(d)).manifest_sha, h1)


if __name__ == "__main__":
    unittest.main()
