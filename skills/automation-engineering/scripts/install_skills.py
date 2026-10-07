#!/usr/bin/env python3
"""Install the Content Factory skills for Claude Code (copies every sibling skill folder).

  python install_skills.py --project D:\\shorts-ai\\factory   # → <project>/.claude/skills/<skill>/
  python install_skills.py --dest ~/.claude/skills           # personal skills directory
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

SKILLS = ["content-factory", "content-research", "trend-intelligence", "content-strategy", "hook-engineering",
          "short-form-script", "multilingual-content", "visual-storyboarding", "voice-production", "video-production",
          "subtitle-production", "video-quality-assurance", "content-analytics", "content-database",
          "automation-engineering", "asset-provenance"]


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--project"); g.add_argument("--dest")
    a = ap.parse_args()
    dest = Path(a.project) / ".claude" / "skills" if a.project else Path(a.dest).expanduser()
    src = Path(__file__).resolve().parents[2]
    dest.mkdir(parents=True, exist_ok=True)
    missing = [s for s in SKILLS if not (src / s / "SKILL.md").exists()]
    if missing:
        raise SystemExit(f"missing skills next to automation-engineering: {missing}")
    for s in SKILLS:
        shutil.copytree(src / s, dest / s, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"installed {len(SKILLS)} skills into {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
