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


if __name__ == "__main__":
    unittest.main()
