"""Regenerate skills/{study,practice}/SKILL.md from method/ (run after editing method files).

Usage: python3 tools/build_skill.py   (from the repo root)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from learnloop.core import practice_skill_text, study_skill_text  # noqa: E402

for name, text in (("study", study_skill_text()), ("practice", practice_skill_text())):
    out = ROOT / "skills" / name / "SKILL.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size} bytes)")
