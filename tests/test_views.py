"""Data for the lesson pane and the Learn page (11 Nov)."""
from learnloop import core

from .conftest import ASSESS, PLAN
from .test_core import skill_message


def test_no_lesson_view(store):
    assert core.lesson_view(store, "s1") == {"lesson": None}


def test_lesson_view_probe(store):
    core.turn_context(store, "s1", skill_message("attention maths"))
    v = core.lesson_view(store, "s1")["lesson"]
    assert v["goal"] == "attention maths" and v["phase"] == "probe" and v["plan"] is None
    assert v["answered"] == 0 and v["open_question"] is None


def test_lesson_view_teach_with_progress(teaching):
    q = teaching.ask("s1", "Which is right here?", options=["a", "b"], correct=0,
                     explanation="Because a is right here.", qtype="check", node_id="dot")
    v = core.lesson_view(teaching, "s1")["lesson"]
    assert v["open_question"] == {"id": q["id"], "prompt": "Which is right here?"}
    teaching.grade(q["id"], answer="A", confidence=90)
    v = core.lesson_view(teaching, "s1")["lesson"]
    assert v["answered"] == 1 and v["correct"] == 1
    assert [(n["id"], n["state"]) for n in v["plan"]["nodes"]] == [("dot", "current"), ("scores", "todo"),
                                                                    ("softmax", "todo")]
    assert v["plan"]["mermaid"].startswith("graph TD") and "class dot current" in v["plan"]["mermaid"]
    # the Desktop map draws from nodes + edges itself (no Mermaid at pane width)
    ids = {n["id"] for n in v["plan"]["nodes"]}
    assert v["plan"]["edges"] and all(len(e) == 2 and set(e) <= ids for e in v["plan"]["edges"])
    assert v["assessment"]["summary"] == ASSESS["summary"]


def test_finished_lesson_still_viewable_in_its_chat(teaching):
    teaching.stop_lesson("s1")
    v = core.lesson_view(teaching, "s1")["lesson"]
    assert v["phase"] == "done"


def test_lessons_overview_and_graph(store):
    core.turn_context(store, "s1", skill_message("attention maths"))
    core.turn_context(store, "s2", skill_message("perceptrons"))
    store.record("s1", [{"name": "Dot product scalar", "statement": "A dot product returns one number."}])
    o = core.lessons_overview(store)
    assert [l["goal"] for l in o["lessons"]] == ["perceptrons", "attention maths"]
    assert o["lessons"][1]["facts"] == 1 and o["stats"]["propositions"] == 1
    g = store.graph()
    assert g["propositions"][0]["name"] == "Dot product scalar"
