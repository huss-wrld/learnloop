"""Question card backend: public view, submission, reveal (11 Nov)."""
import pytest

from learnloop import core
from learnloop.store import LearnError

from .test_core import skill_message


def mc(store, correct=(1,)):
    core.turn_context(store, "s1", skill_message("attention maths"))
    return core.tool_ask(store, "s1", {"prompt": "Which returns a scalar?", "options": ["a+b", "a·b", "a⊙b"],
                                       "correct": list(correct), "explanation": "The dot product sums products."},
                         cards=True)["question_id"]


def free(store):
    core.turn_context(store, "s1", skill_message("attention maths"))
    return core.tool_ask(store, "s1", {"prompt": "Why divide by sqrt(d_k)?", "expected": "Keeps variance at 1."},
                         cards=True)["question_id"]


def test_public_view_hides_key_before_answer(store):
    v = store.public_question(mc(store))
    assert v["options"] == ["a+b", "a·b", "a⊙b"] and v["kind"] == "mc" and v["multi"] is False
    assert "correct" not in v and "explanation" not in v and "expected" not in v and v["status"] == "open"


def test_multi_flag(store):
    assert store.public_question(mc(store, correct=(0, 1)))["multi"] is True


def test_submit_reveals_mc_result(store):
    qid = mc(store)
    v = store.public_question(store.submit(qid, choices=[0], confidence=70, thinking="adding",
                                           reading_thinking="hmm")["id"])
    assert v["result"] == {"verdict": "wrong", "correct": [1], "explanation": "The dot product sums products."}
    assert v["submission"]["confidence"] == 70 and v["submission"]["reading_thinking"] == "hmm"


def test_free_answer_revealed_only_after_grading(store):
    qid = free(store)
    store.submit(qid, text="keeps it small", confidence=30)
    assert "result" not in store.public_question(qid)
    core.tool_grade(store, "s1", {"verdict": "partial"}, cards=True)
    assert store.public_question(qid)["result"] == {"verdict": "partial", "expected": "Keeps variance at 1."}


def test_dont_know_submission(store):
    qid = mc(store)
    v = store.public_question(store.submit(qid, dont_know=True)["id"])
    assert v["result"]["verdict"] == "dont_know" and v["result"]["correct"] == [1]


def test_cannot_submit_twice(store):
    qid = mc(store)
    store.submit(qid, choices=[1])
    with pytest.raises(LearnError, match="already"):
        store.submit(qid, choices=[0])


def test_unknown_question(store):
    with pytest.raises(LearnError, match="Unknown question"):
        store.public_question("q_fake")


def test_card_summary_line(store):
    qid = mc(store)
    q = store.submit(qid, choices=[1], confidence=70, thinking="sum of products")
    line = core.card_answer_line(q)
    assert line.startswith("B) a·b") and "70%" in line and "sum of products" in line


def test_grade_in_card_mode_says_dont_restate(store):
    qid = mc(store)
    store.submit(qid, choices=[1], confidence=90)
    out = core.tool_grade(store, "s1", {}, cards=True)
    assert out["verdict"] == "correct" and "card already showed" in out["next"]


def test_force_cards_setting(store):
    store.set_setting("cards", "force")
    assert core.cards_enabled(store, "cli")


@pytest.mark.parametrize("tool", ["record", "phase_teach", "grade"])
def test_results_before_a_question_say_use_learn_ask(store, tool):
    core.turn_context(store, "s1", skill_message("attention maths"))
    if tool == "record":
        out = core.tool_record(store, "s1", {"propositions": [{"name": "Dot product scalar",
                                                               "statement": "A dot product returns one number."}]})
    elif tool == "grade":
        core.tool_ask(store, "s1", {"prompt": "What does it return?", "expected": "A number."}, cards=False)
        out = core.tool_grade(store, "s1", {"verdict": "correct", "answer": "a number", "confidence": 90}, cards=False)
    else:
        core.tool_phase(store, "s1", {"phase": "plan", "assessment": "Dot: holds it fine",
                                      "plan": "graph TD\n  a[A] --> b[B]"}, cards=False)
        out = core.tool_phase(store, "s1", {"phase": "teach"}, cards=False)
    assert "learn_ask" in out["next"] and "never type a question" in out["next"]


def test_hand_typed_question_is_caught_next_turn(store):
    core.turn_context(store, "s1", skill_message("attention maths"))
    typed = ("**Question.** What is Var(X+Y)?\n\nA) 2\nB) 1\n\nReply with the letter, your confidence "
             "(0/30/50/70/90/100 %), and your thinking.")
    ctx = core.turn_context(store, "s1", "B, 50%", last_reply=typed)
    assert "typed by hand" in ctx and "learn_ask" in ctx
    assert "typed by hand" not in (core.turn_context(store, "s1", "ok", last_reply="Plain explanation.") or "")
