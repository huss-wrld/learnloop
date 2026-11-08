import json
from pathlib import Path

import pytest

from learnloop import core
from learnloop.store import LearnError

from .conftest import ASSESS, PLAN

LH_DATA = Path.home() / ".config/LearnHarness/data"


# ---- method ----
@pytest.mark.parametrize("phase", ["probe", "plan", "teach"])
def test_method_fits_budget_and_has_no_header(phase):
    text = core.method_text(phase)
    assert len(text) <= core.METHOD_BUDGET and "<!--" not in text and "learn_ask" in text


def test_no_learnharness_tool_names_leak():
    for phase in ("probe", "teach"):
        text = core.method_text(phase)
        for name in ("probe_done", "plan_init", "ask_user_question", "nodeId", "dontKnow", "correctAnswer"):
            assert name not in text, name


# ---- /study command: the only way to start ----

def test_command_name_is_not_a_builtin():
    # /learn is a Hermes built-in; plugin commands with built-in names are skipped silently.
    assert '/study <topic>' in core.HELP and '/learn' not in core.HELP

def test_learn_starts_lesson_and_says_go(store):
    out = core.command(store, "s1", "why attention divides by sqrt(d_k)")
    assert "Send **go**" in out and store.active_lesson("s1")["goal"] == "why attention divides by sqrt(d_k)"


def test_learn_help_and_errors_are_text(store):
    assert "/study stop" in core.command(store, "s1", "")
    assert "No active lesson" in core.command(store, "s1", "stop")


def test_learn_stop(store):
    core.command(store, "s1", "attention maths")
    assert "Lesson ended" in core.command(store, "s1", "stop") and store.active_lesson("s1") is None


def test_topic_starting_with_keyword_is_a_topic(store):
    core.command(store, "s1", "map projections in cartography")
    assert store.active_lesson("s1")["goal"] == "map projections in cartography"


def test_recall_toggle(store):
    core.command(store, "s1", "recall on")
    assert store.get_setting("recall") == "on"
    assert "off" in core.command(store, "s1", "recall off")


def test_status_and_map(teaching):
    assert "Phase:** teach" in core.command(teaching, "s1", "status")
    assert "```mermaid" in core.command(teaching, "s1", "map")


# ---- hook: silent unless invoked ----
def test_hook_silent_without_lesson_or_recall(store):
    store.record("s9", [{"name": "Softmax normalises rows", "statement": "Softmax makes each row sum to one."}])
    assert core.turn_context(store, "s1", "tell me about softmax rows") is None


def test_hook_recall_opt_in_with_note(store):
    store.record("s9", [{"name": "Softmax normalises rows", "statement": "Softmax makes each row sum to one."}])
    store.set_setting("recall", "on")
    ctx = core.turn_context(store, "s1", "tell me about softmax rows")
    assert "Softmax normalises rows" in ctx and "used learnloop knowledge" in ctx


def test_hook_lesson_state_and_start_nudge(store):
    core.command(store, "s1", "attention maths")
    ctx = core.turn_context(store, "s1", "go")
    assert "Active lesson" in ctx and "call learn_method" in ctx and "learn_grade" in ctx
    assert core.turn_context(store, "s2", "go") is None  # other chats untouched


def test_hook_flags_card_submission(store):
    core.command(store, "s1", "attention maths")
    q = store.ask("s1", "What does a dot product return?", expected="A number.")
    store.submit(q["id"], text="a number", confidence=90)
    assert "call learn_grade now" in core.turn_context(store, "s1", "")


# ---- tools ----
def test_ask_text_mode_hides_answer(store):
    core.command(store, "s1", "attention maths")
    out = core.tool_ask(store, "s1", {"prompt": "Which returns a scalar?", "options": ["a+b", "a·b"],
                                      "correct": [1], "explanation": "The dot product sums products."}, cards=False)
    assert "A) a+b" in out["show"] and "I don't know" in out["show"] and "sums products" not in out["show"]


def test_ask_card_mode(store):
    core.command(store, "s1", "attention maths")
    out = core.tool_ask(store, "s1", {"prompt": "What does a dot product return?", "expected": "A number."},
                        cards=True)
    assert out["show"] == f'::learnloop-question{{id="{out["question_id"]}"}}'


def test_cards_need_desktop_and_seen_ui(store):
    assert not core.cards_enabled(store, "desktop")      # Desktop half never loaded
    store.set_setting("desktop_ui", "seen")
    assert core.cards_enabled(store, "desktop") and not core.cards_enabled(store, "cli")
    store.set_setting("cards", "off")
    assert not core.cards_enabled(store, "desktop")


def test_grade_flags_confident_miss(store):
    core.command(store, "s1", "attention maths")
    core.tool_ask(store, "s1", {"prompt": "Which returns a scalar?", "options": ["a+b", "a·b"],
                                "correct": [1], "explanation": "The dot product sums products."}, cards=False)
    out = core.tool_grade(store, "s1", {"answer": "A", "confidence": 90, "thinking": "adding"})
    assert out["verdict"] == "wrong" and "Confident miss" in out["next"] and out["correct"] == "B) a·b"


def test_phase_flow_sends_method_only_when_it_changes(store):
    core.command(store, "s1", "attention maths")
    out = core.tool_phase(store, "s1", {"phase": "plan", "assessment": ASSESS}, cards=False)
    assert "method" in out and "Write the plan" in out["next"]
    out = core.tool_phase(store, "s1", {"phase": "plan", "plan": PLAN}, cards=False)
    assert "method" not in out and "```mermaid" in out["map"]
    out = core.tool_phase(store, "s1", {"phase": "teach"}, cards=False)
    assert "method" not in out and out["next"] == "Teach the first node."


def test_recall_tool_respects_opt_in(store):
    with pytest.raises(LearnError, match="recall is off"):
        core.tool_recall(store, "s1", {"query": "softmax"})
    core.command(store, "s1", "attention maths")
    assert core.tool_recall(store, "s1", {"query": "softmax"}) == {"facts": []}


def test_schemas_are_short():
    assert len(json.dumps(core.schemas())) < 6000


# ---- LearnHarness import ----
def write_lh(tmp_path):
    g = tmp_path / "graph"
    g.mkdir()
    nodes = [{"id": "n1", "name": "Value vectors", "statement": "Each token has a value vector v = xW_V."},
             {"id": "n2", "name": "Values don't affect weights", "statement": "Weights come from Q and K only."}]
    chains = [{"id": "c1", "premises": ["n1"], "conclusion": "n2"},
              {"id": "c2", "premises": ["n2"], "conclusion": "n1"}]
    (g / "nodes.jsonl").write_text("\n".join(json.dumps(n) for n in nodes))
    (g / "chains.jsonl").write_text("\n".join(json.dumps(c) for c in chains))
    return tmp_path


def test_import_skips_the_cycle(store, tmp_path):
    out = core.command(store, "s1", f"import {write_lh(tmp_path)}")
    assert "2 new facts" in out and "1 reasoning links" in out and "Skipped 1 circular" in out
    assert "already known" in core.command(store, "s1", f"import {tmp_path}")


@pytest.mark.skipif(not (LH_DATA / "graph/nodes.jsonl").exists(), reason="no local LearnHarness data")
def test_import_real_learnharness_graph(store):
    out = core.command(store, "s1", f"import {LH_DATA}")
    assert "Imported from LearnHarness" in out and store.stats()["propositions"] > 0
