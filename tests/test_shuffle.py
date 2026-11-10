"""Options are shuffled on the way in (after LearnHarness's shuffleOptions): models put the right answer first."""
import collections
import json

import pytest

from learnloop.store import Store, relabel_options

OPTIONS = ["right", "wrong one", "wrong two", "wrong three"]


@pytest.fixture(autouse=True)
def shuffle_on(monkeypatch):
    monkeypatch.setattr(Store, "shuffle_options", True)


def ask_many(store, n=40, correct=(0,)):
    store.start_lesson("s1", "dot products")
    out = []
    for _ in range(n):
        q = store.ask("s1", "Which one is right here?", options=OPTIONS, correct=list(correct),
                      explanation="Because it is the right one.")
        row = store.conn.execute("SELECT options, correct FROM questions WHERE id=?", (q["id"],)).fetchone()
        out.append((q["id"], json.loads(row["options"]), json.loads(row["correct"])))
        store.grade(q["id"], dont_know=True)
    return out


def test_key_follows_the_option(store):
    for _, opts, corr in ask_many(store):
        assert sorted(opts) == sorted(OPTIONS) and [opts[i] for i in corr] == ["right"]


def test_right_answer_is_not_always_first(store):
    spots = collections.Counter(corr[0] for _, _, corr in ask_many(store))
    assert len(spots) >= 3 and spots[0] < 25, spots


def test_multi_select_keeps_both(store):
    for _, opts, corr in ask_many(store, n=10, correct=(0, 2)):
        assert sorted(opts[i] for i in corr) == ["right", "wrong two"]


def test_grading_uses_the_shuffled_key(store):
    store.start_lesson("s1", "dot products")
    q = store.ask("s1", "Which one is right here?", options=OPTIONS, correct=[0], explanation="Because it is the right one.")
    opts = json.loads(store.conn.execute("SELECT options FROM questions WHERE id=?", (q["id"],)).fetchone()["options"])
    store.submit(q["id"], choices=[opts.index("right")], confidence=80, thinking="t")
    assert store.grade(q["id"])["verdict"] == "correct"


def test_explanation_letters_follow_the_shuffle():
    order = [2, 0, 3, 1]  # new position -> old position: old A is now B, old C is now A
    text = "Option A is right. Option C forgets the mean; options B and D add magnitudes. A model of it."
    assert relabel_options(text, order) == \
        "Option B is right. Option A forgets the mean; options D and C add magnitudes. A model of it."


def test_stored_explanation_is_relabelled(store):
    store.start_lesson("s1", "dot products")
    q = store.ask("s1", "Which one is right here?", options=OPTIONS, correct=[0],
                  explanation="Option A is the right one; option B is a trap.")
    row = store.conn.execute("SELECT options, explanation FROM questions WHERE id=?", (q["id"],)).fetchone()
    opts = json.loads(row["options"])
    a, b = "ABCD"[opts.index("right")], "ABCD"[opts.index("wrong one")]
    assert row["explanation"] == f"Option {a} is the right one; option {b} is a trap."
