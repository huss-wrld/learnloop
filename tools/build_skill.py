"""Regenerate skills/study/SKILL.md from method/ (run after editing method files).

Usage: python3 tools/build_skill.py   (from the repo root)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from learnloop.core import study_skill_text  # noqa: E402

out = ROOT / "skills" / "study" / "SKILL.md"
out.write_text(study_skill_text(), encoding="utf-8")
print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size} bytes)")
