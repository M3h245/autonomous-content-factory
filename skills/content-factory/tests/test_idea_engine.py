"""Idea Engine — the batch layer above V3.0.1 (file input, memory filter, scoring, diversity, handoff, isolation).

The production driver is replaced by a stub (`--driver-cmd`): it transplants the packaged-run fixture into the prepared
run and runs the real `factory.py package --zip`, so V3.0.1's own PACKAGE gate, record and memory ingest decide whether a
run is delivered. Nothing here needs an LLM, an API key or the network.

    cd skills && python -m unittest content-factory.tests.test_idea_engine        (~3 min: 5 real `factory.py init`)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# the project root: the first folder above the skills tree that holds memory/dump.json, so the tests work from
# skills/ (root = skills/..) and from the installed .claude/skills/ (root = .claude/..); falls back to ROOT.parent
REPO = next((d for d in ROOT.parents if (d / "memory" / "dump.json").is_file()), ROOT.parent)
for p in (ROOT / "content-factory" / "scripts", ROOT / "content-database" / "scripts"):
    sys.path.insert(0, str(p))
import cfdb  # noqa: E402
import idea_engine as IE  # noqa: E402

PY = sys.executable
ENGINE = ROOT / "content-factory" / "scripts" / "idea_engine.py"
FACT = ROOT / "content-factory" / "scripts" / "factory.py"
CFDB = ROOT / "content-database" / "scripts" / "cfdb.py"
DUMP = Path(__file__).resolve().parent / "fixtures" / "memory_dump_v3.0.0.json"   # frozen test snapshot (= checkpoints/v3.0.0/memory-dump.json), never the live memory
KNUCKLES = REPO / "fixtures" / "phase4_package_run" / "2026-10-07-why-your-knuckles-crack"
CF_ENV = ("CF_DB", "CF_RUNS_DIR", "CF_OUTPUT_DIR", "CF_BATCHES_DIR", "CF_LEARNING", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")

# ---- a realistic ~50-candidate file, as a person would paste it from a chat (built here, not shipped in the engine)
FRESH = [
    ("sky", "Why is the sky blue but sunsets red?", "Sunlight scatters off air molecules and blue scatters most, so at sunset the long path through air leaves only red.",
     "The sky is blue for the same reason sunsets aren't.", "light rays bouncing off air molecules over a horizon", "science", "https://www.nasa.gov/"),
    ("purr", "Why do cats purr?", "Muscles in the larynx twitch 25 to 150 times a second, which means the purr works on the in-breath too.",
     "A cat's purr never stops for breath.", "a cat with a sound wave coming from its throat", "nature", None),
    ("popcorn", "Why does popcorn pop?", "Water inside the kernel turns to steam and the pressure builds until the hull bursts and the starch puffs.",
     "Every popcorn kernel is a tiny pressure cooker.", "a kernel cutaway with steam building inside", "everyday", None),
    ("yawn", "Why is yawning contagious?", "Seeing a yawn triggers the same motor pattern in the brain, which is why even reading about yawns works.",
     "You will probably yawn before this video ends.", "a chain of faces yawning one after another", "psychology", None),
    ("honey", "How do bees turn nectar into honey?", "Bees add an enzyme and fan the nectar with their wings until the water drops below 20 percent.",
     "Honey is nectar that bees dried with their wings.", "bees fanning wings over a honeycomb cell", "nature", None),
    ("compass", "Why does a compass point north?", "The needle is a small magnet that lines up with Earth's magnetic field, which actually points to a south magnetic pole.",
     "Your compass is actually pointing at a south pole.", "a compass needle aligning with field lines around Earth", "science", None),
    ("microwave", "How does a microwave heat food?", "Microwaves make water molecules spin back and forth, and that friction is the heat, so dry food barely warms.",
     "A microwave doesn't heat food. It shakes water.", "water molecules spinning inside a bowl of soup", "technology", None),
    ("bubble", "Why are soap bubbles always round?", "Surface tension pulls the film into the shape with the least area for the air inside, which is a sphere.",
     "A bubble is round because it's lazy.", "a cube-shaped wire frame bubble turning into a sphere", "science", None),
    ("salt", "Why is the ocean salty but rivers are not?", "Rivers carry tiny amounts of salt into the sea, the water evaporates, and the salt stays behind for millions of years.",
     "Rivers make the sea salty, but they taste fresh.", "a river carrying salt grains into the ocean", "nature", None),
    ("ears", "Why do ears pop on a plane?", "Air pressure in the cabin changes faster than the tube behind the eardrum can equalise, so it opens with a pop.",
     "That pop in your ears is a tiny valve opening.", "an eardrum bulging as a plane climbs", "human_body", None),
    ("glowstick", "How do glow sticks glow without heat?", "Snapping the inner tube mixes two chemicals, and the reaction releases energy as light instead of heat.",
     "A glow stick is fire that forgot to get hot.", "a glow stick snapping and lighting up", "science", None),
    ("mirror", "Why do mirrors flip left and right but not up and down?", "A mirror actually flips front to back; we only call it left-right because we turn around in our heads.",
     "Mirrors don't flip left and right. You do.", "a person facing their reflection with arrows", "counterintuitive", None),
    ("octopus", "Why does an octopus have three hearts?", "Two hearts pump blood through the gills and one pumps it to the body, because copper blood carries oxygen poorly.",
     "An octopus has three hearts and blue blood.", "an octopus with three glowing hearts", "nature", None),
    ("anc", "How do noise-cancelling headphones work?", "A microphone hears the noise and the speaker plays the opposite wave, so the two cancel out.",
     "Your headphones fight sound with more sound.", "two sound waves cancelling into a flat line", "technology", None),
    ("goose", "Why do we get goosebumps?", "Tiny muscles pull each hair upright, a leftover from furry ancestors who fluffed up to stay warm.",
     "Goosebumps are fur you no longer have.", "an arm with hairs standing up next to a fluffed cat", "human_body", None),
    ("bread", "Why does bread go stale?", "Stale bread isn't dry: the starch recrystallises, which is why toasting it brings the softness back.",
     "Stale bread isn't dry. It's crystallised.", "bread slices with starch crystals forming", "everyday", None),
    ("penguin", "Why can't penguins fly?", "Their wings became flippers because swimming paid off more than flying, and a body can't be great at both.",
     "Penguins traded the sky for the sea.", "a penguin flipper next to a bird wing", "nature", None),
    ("rainbow", "Why is a rainbow always a curve?", "Each raindrop bends light at the same 42 degree angle from your shadow, so the bow is part of a circle around it.",
     "Every rainbow is actually a full circle.", "a full circular rainbow seen from a plane", "visual_phenomena", None),
    ("twinkle", "Why do stars twinkle but planets don't?", "Stars are points of light that moving air bends back and forth, while planets are tiny discs, so the wobble averages out.",
     "Stars twinkle. Planets don't. Here's the tell.", "a star and a planet in the night sky with air layers", "space", None),
    ("eiffel", "Why is the Eiffel Tower taller in summer?", "Iron expands when it warms, so on a hot day the tower grows by up to 15 centimetres.",
     "The Eiffel Tower grows every summer.", "the tower stretching under the sun", "engineering", None),
    ("chameleon", "How does a chameleon change colour?", "Tiny crystals in its skin move apart or closer together, which changes which light they reflect.",
     "A chameleon doesn't paint its skin. It moves crystals.", "crystals in skin shifting from green to red", "nature", None),
    ("plane", "How does a heavy plane stay in the air?", "The wing pushes air down and the air pushes the wing up, which is why speed matters more than shape.",
     "A plane stays up by throwing air at the ground.", "a wing pushing air downwards", "engineering", None),
    ("asleep", "Why do your feet fall asleep?", "Pressure squeezes the nerves so their signals stop, and the tingling is the nerves waking up again.",
     "Your foot isn't asleep. Its nerves are muted.", "a foot with nerve signals going quiet", "human_body", None),
    ("coffee", "How does coffee keep you awake?", "Caffeine blocks the receptors that adenosine uses to make you sleepy, so the tiredness is still there, just hidden.",
     "Coffee doesn't give you energy. It hides tiredness.", "caffeine molecules blocking keyholes in a brain", "human_body", None),
    ("rod", "How does a lightning rod protect a house?", "It gives the strike an easy metal path to the ground, so the current never goes through the walls.",
     "A lightning rod doesn't stop lightning. It invites it.", "lightning hitting a rod and running into the ground", "engineering", None),
    ("mars", "Why is Mars red?", "Its dust is full of iron oxide, which means the whole planet is basically covered in rust.",
     "Mars is red because it's rusty.", "a rusty nail next to the planet Mars", "space", None),
    ("firefly", "How do fireflies make light?", "A chemical called luciferin reacts with oxygen inside their tail, and almost none of the energy is lost as heat.",
     "Fireflies make light colder than any bulb.", "a firefly tail glowing next to a hot bulb", "nature", None),
    ("hiccup", "Why do we hiccup?", "The diaphragm twitches and the vocal cords snap shut a moment later, which makes the hic sound.",
     "A hiccup is two muscles out of sync.", "a diaphragm twitching under the lungs", "human_body", None),
    ("books", "Why do old books smell sweet?", "As the paper breaks down it releases vanillin, the same molecule that gives vanilla its scent.",
     "Old books smell like vanilla for a real reason.", "an old book with scent lines and a vanilla pod", "everyday", None),
    ("metal", "Why does metal feel colder than wood at the same temperature?", "Metal pulls heat out of your hand faster, so your skin reads speed of heat loss, not temperature.",
     "Metal isn't colder than wood. It's faster.", "a hand touching metal and wood with heat arrows", "counterintuitive", None),
    ("sunflower", "Do sunflowers really follow the sun?", "Young sunflowers do, because the stem grows faster on its shady side by day and the other side at night.",
     "Sunflowers only follow the sun when they're young.", "a field of young sunflowers turning with the sun", "nature", None),
    ("jam", "Why do traffic jams appear from nowhere?", "One driver brakes a little, the next brakes a bit more, and the wave of braking travels backwards down the road.",
     "Most traffic jams have no cause at the front.", "cars on a ring road with a braking wave", "everyday", None),
    ("spider", "Why don't spiders stick to their own webs?", "Only some threads are sticky, and spiders walk on the dry ones with oily, hairy feet.",
     "A spider can get stuck in its own web.", "a spider stepping on dry threads of a web", "nature", None),
    ("touch", "How does a touch screen know where your finger is?", "Your finger carries a little charge, and a grid of wires under the glass feels where the charge changes.",
     "Your phone feels the electricity in your finger.", "a grid of wires under glass with a fingertip", "technology", None),
    ("helium", "Why does helium make your voice squeaky?", "Sound moves faster in helium, so the resonances of your throat shift up, but your vocal cords don't change pitch.",
     "Helium doesn't change your voice's pitch.", "a balloon and sound waves speeding up in a throat", "science", None),
    ("volcano", "Why do some volcanoes explode and others ooze?", "Thick, sticky magma traps gas until it bursts, while runny magma lets the gas escape gently.",
     "A volcano explodes for the same reason a soda does.", "a soda bottle next to an erupting volcano", "nature", None),
    ("weeks", "Why do some years have 53 Mondays?", "A year is 52 weeks plus one day, so the weekday it starts on gets one extra turn.",
     "Leap years aren't every four years.", "a calendar page with an extra Monday highlighted", "common_questions", None),
    ("shadow", "Why are shadows blue in the snow?", "Shadows are lit by the blue sky instead of the sun, so on white snow they turn visibly blue.",
     "Shadows on snow are blue, not grey.", "blue shadows of trees on white snow", "visual_phenomena", None),
]


def make_candidates() -> dict:
    dump = json.loads(DUMP.read_text(encoding="utf-8"))["tables"]
    tube = next(i for i in dump["ideas"] if i["title"].startswith("Shrink the giant Moon"))
    c = []
    for i, topic, angle, hook, visual, cat, src in FRESH:
        c.append({"id": i, "topic": topic, "angle": angle, "hook": hook, "visual": visual, "category": cat,
                  "source_hint": src, "notes": None})
    c += [  # rephrasings of topics the channel already made (memory/dump.json)
        {"id": "mem-knuckles", "topic": "Cracking your knuckles: where does the sound come from?",
         "angle": "The pop is a gas bubble forming in the joint fluid.", "hook": "That knuckle pop isn't your bones.", "category": "human_body"},
        {"id": "mem-onions", "topic": "The real reason chopping onions makes you cry", "angle": "A gas reaches the eye and becomes a mild acid.",
         "category": "everyday"},
        {"id": "mem-tickle", "topic": "Why can't you tickle yourself?", "angle": "The brain predicts your own touch and cancels it.",
         "category": "psychology"},
        {"id": "mem-moon", "topic": "Why the Moon looks huge on the horizon", "angle": "It is an illusion of the brain, not the atmosphere.",
         "category": "space"},
        {"id": "mem-freeze", "topic": "Why does ice cream cause brain freeze?", "angle": "Cold on the palate is felt in the forehead.",
         "category": "human_body"},
        {"id": "mem-tube", "topic": tube["title"], "angle": tube["angle"], "category": "space"},   # an idea already proposed
    ]
    c += [  # in-file near-duplicates (the better-scored phrasing is kept)
        {"id": "purr-2", "topic": "How do cats purr?", "angle": "The voice box vibrates.", "category": "nature"},
        {"id": "sky-2", "topic": "What makes the sky look blue?", "angle": "Air scatters blue light.", "category": "science"},
    ]
    c += [  # weak, misleading or broken entries
        {"id": "listy", "topic": "Top 10 facts about the economy explained in full", "category": "history"},
        {"id": "bait", "topic": "You won't believe what happens inside a black hole", "angle": "Shocking truth.", "category": "space"},
        {"id": "empty", "topic": "   ", "angle": "an entry the chat left blank", "category": "science"},
        {"id": "wrong-type", "topic": "Why do we dream?", "angle": ["not", "a", "string"], "category": "psychology"},
    ]
    return {"version": "1.0", "generated_at": "2026-10-07", "generator": "test", "candidates": c}


def clean_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in CF_ENV}
    env.update(extra)
    return env


def engine(*args, cwd: Path, env: dict | None = None) -> tuple[int, dict | str, str]:
    # the engine prints UTF-8 JSON; force it on Windows pipes (default: the ANSI code page) and decode it as UTF-8
    p = subprocess.run([PY, str(ENGINE), *map(str, args)], capture_output=True, text=True, encoding="utf-8", cwd=cwd,
                       env={**(env or clean_env()), "PYTHONIOENCODING": "utf-8"})
    try:
        out = json.loads(p.stdout)
    except ValueError:
        out = p.stdout
    return p.returncode, out, p.stderr


def tree_sums(d: Path) -> dict:
    return {str(f.relative_to(d)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(d.rglob("*")) if f.is_file()}


STUB = r'''
import json, shutil, subprocess, sys
from pathlib import Path
run, slot, mode, fail = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3], [int(x) for x in sys.argv[4].split(",") if x]
calls = run.parent.parent / "driver_calls.txt"
with calls.open("a") as f:
    f.write(f"{slot} {run.name}\n")
if mode == "noop":
    sys.exit(0)
if slot in fail:
    print("simulated production failure", file=sys.stderr)
    sys.exit(1)
fx = Path(sys.argv[5])
for d in ("research", "ideation", "selection", "videos"):
    shutil.rmtree(run / d, ignore_errors=True)
    shutil.copytree(fx / d, run / d)
st = json.loads((fx / "state.json").read_text(encoding="utf-8"))
own = json.loads((run / "state.json").read_text(encoding="utf-8"))
st.update(run_id=own["run_id"], brief=own["brief"], created_at=own["created_at"])
(run / "state.json").write_text(json.dumps(st, indent=1), encoding="utf-8")
p = subprocess.run([sys.executable, sys.argv[6], "package", "--run", str(run), "--zip"], capture_output=True, text=True)
sys.exit(p.returncode)
'''


def stub_cmd(tmp: Path, mode: str = "ok", fail: str = "") -> str:
    s = tmp / "stub_driver.py"
    s.write_text(STUB, encoding="utf-8")
    return f'"{PY}" "{s}" "{{run}}" {{slot}} {mode} "{fail}" "{KNUCKLES}" "{FACT}"'


def fresh_db(tmp: Path, name: str = "factory.db") -> Path:
    db = tmp / name
    p = subprocess.run([PY, str(CFDB), "import", "--db", str(db), "--in", str(DUMP)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return db


# ============================================================================ 1-5: input file
class IdeasFile(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ie_in_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def raw(self, obj) -> bytes:
        return (obj if isinstance(obj, str) else json.dumps(obj)).encode()

    def test_01_valid_50_candidate_file(self):
        doc = make_candidates()
        self.assertEqual(len(doc["candidates"]), 50)
        _, cands, warns = IE.parse_ideas(self.raw(doc))
        self.assertEqual(len(cands), 50)                     # nothing dropped
        self.assertEqual(warns, [])
        self.assertEqual(sorted(c["id"] for c in cands if not c["valid"]), ["empty", "wrong-type"])
        self.assertEqual(cands[0]["source_hint"], ["https://www.nasa.gov/"])
        self.assertEqual(cands[1]["source_hint"], [])
        (self.tmp / "ideas.json").write_text(json.dumps(doc), encoding="utf-8")
        rc, out, _ = engine("validate", "--ideas-file", self.tmp / "ideas.json", cwd=self.tmp)
        self.assertEqual(rc, 0)
        self.assertEqual((out["valid"], out["candidates"], out["usable"]), (True, 50, 48))
        self.assertEqual({x["id"] for x in out["invalid"]}, {"empty", "wrong-type"})

    def test_02_malformed_json_is_rejected_with_its_position(self):
        bad = '{"version": "1.0", "candidates": [{"id": "a", "topic": "Why?"},]}'
        with self.assertRaises(IE.IdeaFileError) as e:
            IE.parse_ideas(self.raw(bad))
        self.assertRegex(e.exception.problems[0], r"not valid JSON: .* line 1, column \d+")
        (self.tmp / "ideas.json").write_text(bad, encoding="utf-8")
        rc, out, _ = engine("select", "--ideas-file", self.tmp / "ideas.json", "--batches-dir", self.tmp / "b",
                            "--db", fresh_db(self.tmp), cwd=self.tmp)
        self.assertEqual((rc, out["error"]), (2, "INVALID_IDEAS_FILE"))
        self.assertFalse(any((self.tmp / "b").glob("*/manifest.json")))      # no batch from a broken file
        for txt in ("", "[]", '"ideas"', '{"version": "1.0", "candidates": [{"id": "a", "topic": "x", "topic": "y"}]}'):
            with self.assertRaises(IE.IdeaFileError, msg=txt):
                IE.parse_ideas(self.raw(txt))

    def test_03_missing_or_empty_candidates_list(self):
        for doc in ({"version": "1.0"}, {"version": "1.0", "candidates": []}, {"version": "1.0", "candidates": {"a": 1}}):
            with self.assertRaises(IE.IdeaFileError) as e:
                IE.parse_ideas(self.raw(doc))
            self.assertIn('"candidates" must be a non-empty list', e.exception.problems)
        with self.assertRaises(IE.IdeaFileError) as e:
            IE.parse_ideas(self.raw({"version": "2", "candidates": [{"id": "a", "topic": "t"}]}))
        self.assertIn('"version" must be "1.0"', e.exception.problems[0])

    def test_04_empty_topic_marks_only_that_candidate(self):
        doc = {"version": "1.0", "candidates": [{"id": "a", "topic": "Why do cats purr?"}, {"id": "b", "topic": ""},
                                                 {"id": "c"}, {"id": "d", "topic": None}, {"id": "e", "topic": "x" * 201}]}
        _, cands, _ = IE.parse_ideas(self.raw(doc))
        self.assertEqual([c["valid"] for c in cands], [True, False, False, False, False])
        self.assertIn('missing or empty "topic"', cands[1]["problems"])
        self.assertIn('"topic" longer than 200 characters', cands[4]["problems"])

    def test_05_duplicate_and_bad_ids(self):
        doc = {"version": "1.0", "candidates": [{"id": "a", "topic": "t1"}, {"id": "a", "topic": "t2"}, {"topic": "t3"},
                                                 {"id": "has space", "topic": "t4"}]}
        with self.assertRaises(IE.IdeaFileError) as e:
            IE.parse_ideas(self.raw(doc))
        msg = " ".join(e.exception.problems)
        self.assertIn("duplicate candidate id(s): ['a']", msg)
        self.assertIn("#3", msg)
        self.assertIn("#4", msg)

    def test_schema_and_example_agree_with_the_engine(self):
        from cf_common import validate
        schema = json.loads((ROOT / "content-factory" / "schemas" / "idea_candidates.schema.json").read_text(encoding="utf-8"))
        example = json.loads((REPO / "input" / "ideas.example.json").read_text(encoding="utf-8"))
        self.assertEqual(validate(example, schema), [])
        _, cands, _ = IE.parse_ideas(json.dumps(example).encode())
        self.assertTrue(all(c["valid"] for c in cands))
        doc = make_candidates()
        errs = validate(doc, schema)            # the type error is flagged by the schema; a whitespace-only topic only by
        flagged = {doc["candidates"][int(e.split("[")[1].split("]")[0])]["id"] for e in errs}   # the pattern / the engine
        self.assertEqual(flagged, {"wrong-type"})
        self.assertEqual(schema["properties"]["candidates"]["items"]["properties"]["topic"]["pattern"], "\\S")

    def test_unknown_fields_are_reported_not_fatal(self):
        _, cands, _ = IE.parse_ideas(self.raw({"version": "1.0", "candidates": [{"id": "a", "topic": "t", "score": 9}]}))
        self.assertTrue(cands[0]["valid"])
        self.assertIn("unknown field(s) ['score'] ignored", cands[0]["warnings"])  # a user-supplied score is never used
        self.assertNotIn("score", cands[0])


# ============================================================================ 6-9, 11-12: selection
class Selection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="ie_sel_"))
        cls.db = fresh_db(cls.tmp)
        cls.ideas = cls.tmp / "ideas.json"
        cls.ideas.write_text(json.dumps(make_candidates(), indent=1), encoding="utf-8")
        cls.history_before = hashlib.sha256(cls.db.read_bytes()).hexdigest()
        # --count 5: this class checks a full five-topic selection (the default is 2; see test_video_count)
        cls.rc, cls.out, cls.err = engine("select", "--ideas-file", cls.ideas, "--batches-dir", cls.tmp / "batches", "--db", cls.db,
                                          "--count", 5, cwd=cls.tmp, env=clean_env())     # no API keys in the environment
        cls.batch = Path(cls.out["batch"]) if isinstance(cls.out, dict) and "batch" in cls.out else None
        cls.rc2, cls.out2, _ = engine("select", "--ideas-file", cls.ideas, "--batches-dir", cls.tmp / "batches", "--db", cls.db,
                                      "--count", 5, "--allow-reused-input", cwd=cls.tmp)
        cls.rc3, cls.out3, _ = engine("select", "--ideas-file", cls.ideas, "--batches-dir", cls.tmp / "batches", "--db", cls.db,
                                      "--count", 5, cwd=cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def j(self, name, batch=None):
        return json.loads(((batch or self.batch) / name).read_text(encoding="utf-8"))

    def test_selects_without_any_api_key(self):
        self.assertEqual(self.rc, 0, f"{self.out}\n{self.err[-2000:]}")
        src = ENGINE.read_text(encoding="utf-8")
        for mod in ("anthropic", "openai", "requests", "urllib.request"):
            self.assertNotIn(f"import {mod}", src)

    def test_batch_layout(self):
        for name in ("input.json", "candidates.json", "filtered.json", "research.json", "ranking.json", "selected.json",
                     "manifest.json", "report.json", "report.md"):
            self.assertTrue((self.batch / name).exists(), name)
        self.assertEqual((self.batch / "input.json").read_bytes(), self.ideas.read_bytes())
        self.assertEqual(self.j("candidates.json")["count"], 50)

    def test_06_memory_rejects_repeats_and_rephrasings(self):
        rej = {r["id"]: r for r in self.j("report.json")["rejected"]}
        for i in ("mem-knuckles", "mem-onions", "mem-tickle", "mem-moon", "mem-freeze", "mem-tube"):
            self.assertEqual(rej[i]["stage"], "memory", i)
        self.assertIn("novelty", rej["mem-tube"]["reason"])               # SELECTION's novelty rule, not just init's
        self.assertIn("repeats earlier", rej["mem-knuckles"]["reason"])
        flt = {c["id"]: c for c in self.j("filtered.json")["candidates"]}
        self.assertEqual(flt["mem-knuckles"]["compared_with"], 16)          # 8 run topics + 8 video titles
        self.assertTrue(flt["weeks"]["hook_repeats_past"])                  # a used hook is flagged and penalised
        self.assertEqual(self.history_before, hashlib.sha256(self.db.read_bytes()).hexdigest())  # selection writes no memory

    def test_06b_memory_rule_is_the_one_factory_init_enforces(self):
        topic = next(c for c in make_candidates()["candidates"] if c["id"] == "mem-onions")["topic"]
        p = subprocess.run([PY, str(FACT), "init", "--topic", topic, "--runs-dir", str(self.tmp / "initcheck"), "--db", str(self.db)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stdout)["error"], "TOPIC_REPEATED")

    def test_invalid_and_misleading_are_reported_not_dropped(self):
        rep = self.j("report.json")
        self.assertEqual({r["id"] for r in rep["invalid"]}, {"empty", "wrong-type"})
        rej = {r["id"]: r for r in rep["rejected"]}
        self.assertEqual(rej["bait"]["stage"], "quality")
        self.assertEqual(rej["listy"]["stage"], "quality")                  # an empty overview is below the floor
        self.assertIn("below the floor", rej["listy"]["reason"])
        accounted = {r["id"] for r in rep["rejected"]} | {w["id"] for w in rep["winners"]} | \
            {n["id"] for n in self.j("selected.json")["not_selected"]}
        self.assertEqual(accounted, {c["id"] for c in make_candidates()["candidates"]})   # every candidate has an outcome

    def test_07_ranking_is_explained_and_ordered(self):
        rk = self.j("ranking.json")
        self.assertEqual(rk["weights"], IE.WEIGHTS)
        rows = rk["ranked"]
        self.assertEqual([r["rank"] for r in rows], list(range(1, len(rows) + 1)))
        self.assertEqual(rows, sorted(rows, key=lambda r: (-r["total"], r["position"])))
        for r in rows:
            self.assertEqual(set(r["components"]), set(IE.WEIGHTS))
            self.assertAlmostEqual(r["total"], sum(IE.WEIGHTS[k] * r["components"][k] for k in IE.WEIGHTS), places=3)
            self.assertTrue(all(r["reasons"][k] for k in IE.WEIGHTS), r["id"])
        by = {r["id"]: r for r in rows}
        self.assertGreater(by["mirror"]["total"], by["listy"]["total"])     # a single sharp question beats an overview

    def test_08_winners_are_diverse(self):
        w = self.j("selected.json")["winners"]
        for i, a in enumerate(w):
            for b in w[i + 1:]:
                self.assertIsNone(IE.same_subject(a["topic"], b["topic"]), (a["id"], b["id"]))
        rej = {r["id"]: r for r in self.j("report.json")["rejected"]}
        self.assertEqual(rej["purr-2"]["stage"], "duplicate")
        self.assertIn("purr", rej["purr-2"]["reason"])
        self.assertEqual(rej["sky-2"]["stage"], "duplicate")
        self.assertTrue(all(len(x["why"]) == 3 for x in w))
        self.assertTrue(all("selection" in x and "marginal_score" in x["selection"] for x in w))

    def test_09_exactly_five(self):
        self.assertEqual(len(self.j("selected.json")["winners"]), 5)
        self.assertEqual([s["slot"] for s in self.j("manifest.json")["selected"]], [1, 2, 3, 4, 5])

    def test_11_deterministic(self):
        self.assertEqual(self.rc2, 0)
        b2 = Path(self.out2["batch"])
        self.assertNotEqual(b2, self.batch)                                 # a new batch, never the old folder
        for name in ("ranking.json", "selected.json", "filtered.json", "research.json"):
            self.assertEqual(self.j(name), self.j(name, b2), name)
        m1, m2 = self.j("manifest.json"), self.j("manifest.json", b2)
        self.assertEqual(m1["selected"], m2["selected"])
        self.assertEqual(m1["memory"]["history_sha256"], m2["memory"]["history_sha256"])

    def test_11b_ties_break_on_file_position(self):
        a = {"id": "x1", "topic": "Why do zebras have stripes?", "position": 1, "score": {"total": 0.6}}
        b = {"id": "x2", "topic": "How do glaciers move downhill?", "position": 2, "score": {"total": 0.6}}
        for _ in range(3):
            chosen, _ = IE.select([dict(b), dict(a)])
            self.assertEqual(chosen[0]["id"], "x1")

    def test_12_manifest(self):
        m = self.j("manifest.json")
        self.assertEqual(m["schema"], "cf-idea-batch/1")
        self.assertEqual(m["batch_id"], self.batch.name)
        self.assertEqual(m["ideas_file"]["sha256"], hashlib.sha256(self.ideas.read_bytes()).hexdigest())
        self.assertEqual(m["memory"]["db"], str(self.db.resolve()))
        self.assertEqual(m["factory_version"], (ROOT / "content-factory" / "VERSION").read_text(encoding="utf-8").strip())
        self.assertEqual(m["production"]["init"], {"count": 1, "languages": "en", "min_s": 20.0, "max_s": 45.0})
        self.assertEqual(m["manifest_sha256"], IE.sha256_bytes(IE.canonical(IE.manifest_core(m)).encode()))
        sel = {w["id"] for w in self.j("selected.json")["winners"]}
        self.assertEqual({s["id"] for s in m["selected"]}, sel)

    def test_16a_reused_ideas_file_is_refused(self):
        self.assertEqual((self.rc3, self.out3["error"]), (2, "IDEAS_FILE_ALREADY_USED"))
        self.assertIn(self.batch.name, self.out3["batches"])

    def test_16b_edited_manifest_is_refused(self):
        b = Path(self.out2["batch"])
        saved = (b / "manifest.json").read_bytes()
        try:
            m = self.j("manifest.json", b)
            m["selected"][0]["topic"] = "Why do zebras have stripes?"
            (b / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
            rc, out, _ = engine("produce", "--batch", b, "--produce", "none", cwd=self.tmp)
            self.assertEqual((rc, out["error"]), (2, "STALE_MANIFEST"))
            self.assertIn("changed after selection", out["why"])
            (b / "manifest.json").write_bytes(saved)
            (b / "input.json").write_text("{}", encoding="utf-8")                              # the archived input swapped
            rc, out, _ = engine("produce", "--batch", b, "--produce", "none", cwd=self.tmp)
            self.assertEqual((rc, out["error"]), (2, "STALE_MANIFEST"))
            self.assertIn("input.json", out["why"])
            self.assertFalse((b / "runs").exists())                          # nothing was prepared from it
        finally:
            (b / "manifest.json").write_bytes(saved)
            (b / "input.json").write_bytes(self.ideas.read_bytes())

    def test_16g_memory_gone_before_production_is_refused(self):
        db2 = self.tmp / "gone.db"
        shutil.copy(self.db, db2)
        rc, out, _ = engine("select", "--ideas-file", self.ideas, "--batches-dir", self.tmp / "batches-gone", "--db", db2,
                            cwd=self.tmp)
        self.assertEqual(rc, 0, out)
        b = Path(out["batch"])
        db2.unlink()
        rc, out, _ = engine("produce", "--batch", b, "--produce", "none", cwd=self.tmp)
        self.assertEqual((rc, out["error"]), (2, "MEMORY_MISSING"))
        self.assertFalse(db2.exists())                                       # no silently empty memory created
        self.assertFalse((b / "runs").exists())

    def test_no_memory_is_an_environment_error(self):
        empty = self.tmp / "nomem"
        empty.mkdir()
        rc, out, _ = engine("select", "--ideas-file", self.ideas, "--batches-dir", empty / "b", "--db", empty / "absent.db", cwd=empty)
        self.assertEqual((rc, out["error"]), (3, "NO_MEMORY"))
        self.assertFalse((empty / "absent.db").exists())


# ============================================================================ 10: too few
class TooFew(unittest.TestCase):
    def test_10_fewer_than_five_fails_clearly(self):
        tmp = Path(tempfile.mkdtemp(prefix="ie_few_"))
        try:
            all_c = {c["id"]: c for c in make_candidates()["candidates"]}
            pick = ["sky", "sky-2", "purr", "purr-2", "mirror", "mem-onions", "mem-tickle", "empty", "bait"]
            (tmp / "ideas.json").write_text(json.dumps({"version": "1.0", "candidates": [all_c[i] for i in pick]}), encoding="utf-8")
            rc, out, _ = engine("run", "--ideas-file", tmp / "ideas.json", "--batches-dir", tmp / "b", "--db", fresh_db(tmp),
                                "--count", 5, "--driver-cmd", "false", cwd=tmp)
            self.assertEqual((rc, out["error"], out["usable"], out["need"]), (2, "TOO_FEW_CANDIDATES", 3, 5))
            b = Path(out["batch"])
            self.assertFalse((b / "manifest.json").exists())
            self.assertFalse((b / "runs").exists())
            rep = json.loads((b / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(rep["stage"], "selection_failed")
            self.assertEqual(len(rep["rejected"]), 6)
            self.assertIn("only 3 usable", (b / "report.md").read_text(encoding="utf-8"))
            rc, out, _ = engine("produce", "--batch", b, cwd=tmp)
            self.assertEqual((rc, out["error"]), (2, "NO_MANIFEST"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================ 13-16: handoff, isolation, failure, stale
class Production(unittest.TestCase):
    """prepare (5 × factory.py init) → produce with slot 3 failing → produce again (slot 3 recovers, the others are left
    alone) → stale package result and a changed output folder are refused."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="ie_prod_"))
        cls.db = fresh_db(cls.tmp)
        cls.ideas = cls.tmp / "ideas.json"
        cls.ideas.write_text(json.dumps(make_candidates()), encoding="utf-8")
        cls.out_dir = cls.tmp / "hdd"
        cls.other_runs = cls.tmp / "other-runs"                 # the owner's normal runs folder: must stay untouched
        (cls.other_runs / "keep").mkdir(parents=True)
        (cls.other_runs / "keep" / "state.json").write_text("{}", encoding="utf-8")
        (cls.tmp / "memory").mkdir()                         # a project folder: memory/dump.json is exported after production
        env = clean_env(CF_RUNS_DIR=str(cls.other_runs))
        cls.prep = engine("run", "--ideas-file", cls.ideas, "--batches-dir", cls.tmp / "batches", "--db", cls.db,
                          "--count", 5, "--produce", "none", cwd=cls.tmp, env=env)
        cls.batch = Path(cls.prep[1]["batch"])
        cls.slots0 = json.loads((cls.batch / "slots.json").read_text(encoding="utf-8"))["slots"]
        cls.states0 = [json.loads((Path(x["run_dir"]) / "state.json").read_text(encoding="utf-8")) for x in cls.slots0 if x["run_dir"]]
        cls.first = engine("produce", "--batch", cls.batch, "--output-dir", cls.out_dir,
                           "--driver-cmd", stub_cmd(cls.tmp, "ok", "3"), cwd=cls.tmp, env=env)
        cls.rep1 = json.loads((cls.batch / "report.json").read_text(encoding="utf-8"))
        cls.sums1 = {s["slot"]: tree_sums(Path(s["output"])) for s in cls.rep1["runs"] if s.get("output")}
        cls.calls1 = (cls.batch / "driver_calls.txt").read_text(encoding="utf-8").split("\n")
        cls.second = engine("produce", "--batch", cls.batch, "--output-dir", cls.out_dir,
                            "--driver-cmd", stub_cmd(cls.tmp, "ok", ""), cwd=cls.tmp, env=env)
        cls.rep2 = json.loads((cls.batch / "report.json").read_text(encoding="utf-8"))
        cls.sums2 = {s["slot"]: tree_sums(Path(s["output"])) for s in cls.rep2["runs"] if s.get("output")}
        cls.calls2 = (cls.batch / "driver_calls.txt").read_text(encoding="utf-8").split("\n")
        # stale: slot 1's package result is edited after V3.0.1 recorded it; slot 2's delivered copy differs from its run
        r1 = Path(cls.slots0[0]["run_dir"])
        res = r1 / "package" / "v01" / "result.json"
        res.write_text(res.read_text(encoding="utf-8") + " ", encoding="utf-8")
        out2 = Path(next(s["output"] for s in cls.rep2["runs"] if s["slot"] == 2))
        (out2 / "package" / "run_summary.md").write_text("edited on the HDD\n", encoding="utf-8")
        (out2 / "package" / "checksums.sha256").write_text("0" * 64 + "  run_summary.md\n", encoding="utf-8")
        cls.third = engine("produce", "--batch", cls.batch, "--output-dir", cls.out_dir,
                           "--driver-cmd", stub_cmd(cls.tmp, "noop", ""), cwd=cls.tmp, env=env)
        cls.rep3 = json.loads((cls.batch / "report.json").read_text(encoding="utf-8"))
        cls.out2_after = tree_sums(out2)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def slot(self, rep, n):
        return next(s for s in rep["runs"] if s["slot"] == n)

    def test_13_handoff_creates_five_v301_runs(self):
        rc, out, err = self.prep
        self.assertEqual(rc, 0, f"{out}\n{err[-2000:]}")
        self.assertEqual(out["stage"], "prepared")
        m = json.loads((self.batch / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(self.slots0), 5)
        for s, w in zip(self.slots0, m["selected"]):
            run = Path(s["run_dir"])
            self.assertEqual(run.parent, self.batch / "runs")
            brief = json.loads((run / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(brief["topic"], w["topic"])
            self.assertEqual((brief["count"], brief["languages"], brief["hook_engine"]), (1, ["en"], "v2"))
            self.assertEqual(brief["memory"]["db"], str(self.db.resolve()))      # the one shared memory
            self.assertEqual(brief["memory"]["topic_check"]["repeats"], [])      # init re-checked the topic itself
            self.assertIn(f"Angle (from the idea batch): {w['angle']}", brief["constraints"])
        for st in self.states0:                                                  # V3.0.1 does all production work
            self.assertEqual((st["status"], st["global"]["RESEARCH"]["status"], st["videos"]), ("in_progress", "pending", {}))

    def test_14_runs_are_isolated(self):
        dirs = [Path(s["run_dir"]) for s in self.slots0]
        self.assertEqual(len({d.name for d in dirs}), 5)
        self.assertEqual(sorted(p.name for p in (self.other_runs).iterdir()), ["keep"])   # CF_RUNS_DIR untouched
        outs = [Path(self.slot(self.rep2, n)["output"]) for n in range(1, 6)]
        self.assertEqual(len({o for o in outs}), 5)
        for n, o in enumerate(outs, 1):
            run_name = Path(self.slot(self.rep2, n)["run_dir"]).name        # "YYYY-MM-DD-slug"
            self.assertEqual(o.parent, self.out_dir.resolve())             # flat: no batch-id wrapper
            self.assertEqual(o.name, f"{run_name[:10]}_{n:02d}_{run_name[11:]}")
            self.assertTrue((o / "package" / "v01" / "final.mp4").exists())
            self.assertTrue(any(o.glob("*_package.zip")))

    def test_15_one_failed_run_does_not_touch_the_others(self):
        rc, out, _ = self.first
        self.assertEqual(rc, 2)
        self.assertEqual(out["stage"], "production_incomplete")
        self.assertEqual(out["succeeded"], [1, 2, 4, 5])
        s3 = self.slot(self.rep1, 3)
        self.assertEqual(s3["status"], "not_packaged")
        self.assertEqual(s3["reasons"][0], "driver exit 1")
        self.assertTrue(s3["log"].endswith(".1.log"))
        self.assertIn("simulated production failure", Path(s3["log"]).read_text(encoding="utf-8"))
        self.assertNotIn("output", s3)
        for n in (1, 2, 4, 5):
            s = self.slot(self.rep1, n)
            self.assertEqual((s["status"], s["output_note"]), ("packaged", "copied and verified"))
        self.assertIn("| 3 |", (self.batch / "report.md").read_text(encoding="utf-8"))
        # rerun: only the failed slot is driven again; the delivered ones are byte-identical
        rc, out, _ = self.second
        self.assertEqual((rc, out["stage"], out["succeeded"]), (0, "delivered", [1, 2, 3, 4, 5]))
        new_calls = [c for c in self.calls2[len(self.calls1) - 1:] if c]
        self.assertEqual([c.split()[0] for c in new_calls], ["3"])
        for n in (1, 2, 4, 5):
            self.assertEqual(self.sums1[n], self.sums2[n], n)
            self.assertEqual(self.slot(self.rep2, n)["output_note"], "already delivered")

    def test_15b_produced_topics_enter_the_shared_memory(self):
        con = cfdb.connect(str(self.db))
        topics = {r[0] for r in con.execute("SELECT topic FROM runs")}
        con.close()
        m = json.loads((self.batch / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue({w["topic"] for w in m["selected"]} <= topics)
        dump = json.loads((self.tmp / "memory" / "dump.json").read_text(encoding="utf-8"))       # as run_factory.* export it
        self.assertTrue({w["topic"] for w in m["selected"]} <= {r["topic"] for r in dump["tables"]["runs"]})
        self.assertEqual(self.rep2["memory_export"], str((self.tmp / "memory" / "dump.json").resolve()))
        rc, out, _ = engine("select", "--ideas-file", self.ideas, "--batches-dir", self.tmp / "batches2", "--db", self.db,
                            cwd=self.tmp)
        self.assertEqual(rc, 0, out)
        rej = {r["id"]: r for r in json.loads((Path(out["batch"]) / "report.json").read_text(encoding="utf-8"))["rejected"]}
        for w in m["selected"]:
            self.assertEqual(rej[w["id"]]["stage"], "memory", w["id"])            # never selected twice

    def test_16c_stale_package_result_is_not_delivered(self):
        rc, out, _ = self.third
        self.assertEqual(rc, 2)
        s1 = self.slot(self.rep3, 1)
        self.assertEqual(s1["status"], "not_packaged")
        self.assertTrue(any("differs from the one V3.0.1 recorded" in r for r in s1["reasons"]), s1["reasons"])
        self.assertEqual(tree_sums(Path(self.slot(self.rep2, 1)["output"])), self.sums2[1])   # earlier delivery intact

    def test_16d_changed_output_folder_is_never_overwritten(self):
        s2 = self.slot(self.rep3, 2)
        self.assertEqual(s2["status"], "delivery_failed")
        self.assertIn("not overwritten", s2["reasons"][0])
        self.assertIn("edited on the HDD\n", (Path(s2["output"]) / "package" / "run_summary.md").read_text(encoding="utf-8"))
        self.assertEqual(self.out2_after, tree_sums(Path(s2["output"])))

    def test_16e_foreign_or_missing_runs_are_refused(self):
        b = self.batch
        slots = json.loads((b / "slots.json").read_text(encoding="utf-8"))
        saved = json.dumps(slots)
        try:
            slots["slots"][3]["run_dir"] = str(self.other_runs / "keep")              # outside this batch
            slots["slots"][4]["run_dir"] = str(b / "runs" / "no-such-run")              # missing
            (b / "slots.json").write_text(json.dumps(slots), encoding="utf-8")
            before = (b / "driver_calls.txt").read_text(encoding="utf-8")
            rc, out, _ = engine("produce", "--batch", b, "--driver-cmd", stub_cmd(self.tmp, "noop", ""), cwd=self.tmp)
            rep = json.loads((b / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(rc, 2)
            self.assertEqual(self.slot(rep, 4)["status"], "refused")
            self.assertIn("not a run of this batch", self.slot(rep, 4)["reasons"][0])
            self.assertEqual(self.slot(rep, 5)["status"], "refused")
            self.assertIn("missing", self.slot(rep, 5)["reasons"][0])
            calls = (b / "driver_calls.txt").read_text(encoding="utf-8")[len(before):].split()
            self.assertNotIn("4", calls[::2])
            self.assertNotIn("5", calls[::2])
            self.assertEqual(sorted(p.name for p in self.other_runs.iterdir()), ["keep"])
            self.assertEqual((self.other_runs / "keep" / "state.json").read_text(encoding="utf-8"), "{}")
        finally:
            (b / "slots.json").write_text(saved, encoding="utf-8")

    def test_16f_one_producer_per_batch(self):
        lock = self.batch / ".lock"
        lock.write_text(json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "since": "now", "cmd": "test"}), encoding="utf-8")
        try:
            rc, out, err = engine("produce", "--batch", self.batch, "--produce", "none", cwd=self.tmp)
            self.assertNotEqual(rc, 0)
            self.assertIn("LOCKED", err + str(out))
        finally:
            lock.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
