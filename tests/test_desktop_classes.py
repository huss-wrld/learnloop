"""Desktop compiles Tailwind from its own sources, so a class only it never uses does nothing in a plugin
(KI-19). Every class in desktop/plugin.js must appear somewhere in Desktop's source."""
import os
import re
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / "desktop" / "plugin.js"
DESKTOP_SRC = Path(os.environ.get("HERMES_DESKTOP_SRC", Path.home() / "Projects/learnloop-ref/hermes-v0.23.0/apps/desktop/src"))
UTILITY = re.compile(r"^(?:hover:)?(?:flex|text-|bg-|border|rounded|p[xylr]?-|gap-|w-|h-|max-|min-|font-|self-|items-|"
                     r"justify|overflow|shadow|line-clamp|absolute|relative|inset|top-|right-|m[xyl]?-|leading|"
                     r"tracking|uppercase|shrink|cursor|block|truncate|\[&)")


@pytest.mark.skipif(not DESKTOP_SRC.is_dir(), reason="needs a Hermes Desktop source checkout")
def test_plugin_classes_exist_in_desktop():
    tokens = {t for s in re.findall(r"'([^'\n]*)'", JS.read_text(encoding="utf-8")) for t in s.split()
              if UTILITY.match(t)}
    corpus = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in DESKTOP_SRC.rglob("*")
                        if p.suffix in (".ts", ".tsx", ".css") and ".test." not in p.name)
    missing = sorted(t for t in tokens if t not in corpus)
    assert not missing, f"classes Desktop never compiles (use inline styles or the STYLE sheet): {missing}"
