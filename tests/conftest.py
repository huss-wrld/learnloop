import sqlite3
import sys
from pathlib import Path

import pytest

# `import learnloop` resolves to this repo (the repo folder is named `learnloop`).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from learnloop.store import Store  # noqa: E402

PLAN = "graph TD\n  dot[Dot product] --> scores[Score matrix]\n  scores --> softmax[Row softmax]"
ASSESS = {"strands": [{"strand": "dot product", "assessment": "Computes it inside matmul; no geometry."}],
          "summary": "Enter from matrix multiplication."}


@pytest.fixture(autouse=True)
def fixed_option_order(monkeypatch):
    """Most tests answer by position; test_shuffle.py turns the shuffle back on."""
    monkeypatch.setattr(Store, "shuffle_options", False)


@pytest.fixture
def store():
    return Store(sqlite3.connect(":memory:", check_same_thread=False))


@pytest.fixture
def teaching(store):
    """A store with an active lesson in the teach phase for session s1."""
    store.start_lesson("s1", "understand attention maths")
    store.set_phase("s1", "plan", assessment=ASSESS, plan=PLAN)
    store.set_phase("s1", "teach")
    return store
