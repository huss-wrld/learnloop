"""Practice sessions (LearnHarness practice: problem -> thinking/hints -> conclude -> pause -> next)."""
import pytest

from learnloop.store import LearnError

SOL = "Var(q.k) = d_k because each term has variance 1 and independent variances add."


@pytest.fixture()
def graph(store):
    store.record("", [
        {"name": "Variances add", "statement": "For independent X and Y, Var(X+Y) = Var(X) + Var(Y)."},
        {"name": "Products multiply variances", "statement": "For independent mean-zero q and k, Var(qk) = Var(q)Var(k)."},
        {"name": "Dot product variance", "statement": "With unit-variance components, Var(q.k) = d_k."},
        {"name": "Unrelated fact", "statement": "Paris is the capital of France, which is unrelated."},
    ], [{"premises": ["Variances add", "Products multiply variances"], "conclusion": "Dot product variance"}])
    return store


@pytest.fixture()
def practising(graph):
    ids = graph.neighbourhood([graph.search("dot product variance", 1)[0]["id"]])
    graph.start_practice("s1", "dot product variance", ids)
    return graph


def test_neighbourhood_pulls_in_premises_not_strangers(graph):
    pid = graph.search("dot product variance", 1)[0]["id"]
    names = {p["name"] for p in graph.material(graph.start_practice("s9", "x y z", graph.neighbourhood([pid]))["id"])["propositions"]}
    assert names == {"Dot product variance", "Variances add", "Products multiply variances"}


def test_material_includes_chains(practising):
    les = practising.active_lesson("s1")
    m = practising.material(les["id"])
    assert m["chains"] == [{"premises": ["Variances add", "Products multiply variances"],
                            "conclusion": "Dot product variance"}]


def test_pose_needs_solution_and_mode(practising):
    with pytest.raises(LearnError, match="modelSolution is required"):
        practising.pose("s1", "What is Var(q.k) for d_k = 64?", "recall", "")
    with pytest.raises(LearnError, match="mode must be one of"):
        practising.pose("s1", "What is Var(q.k) for d_k = 64?", "quiz", SOL)


def test_one_problem_at_a_time_then_pause(practising):
    p = practising.pose("s1", "What is Var(q.k) for d_k = 64?", "recall", SOL, target=["Dot product variance"])
    assert p["targets"] and p["status"] == "open"
    with pytest.raises(LearnError, match="still active"):
        practising.pose("s1", "Another problem statement here", "recall", SOL)
    done = practising.conclude("s1", "solved", "Used both rules in order.", rung=None, miss_class=None)
    assert done["status"] == "concluded" and done["outcome"] == "solved"
    with pytest.raises(LearnError, match="Paused after the last problem"):
        practising.pose("s1", "Another problem statement here", "discrimination", SOL)
    assert practising.resume("s1") is True
    assert practising.pose("s1", "Another problem statement here", "discrimination", SOL)["status"] == "open"


def test_solution_hidden_until_concluded(practising):
    p = practising.pose("s1", "What is Var(q.k) for d_k = 64?", "recall", SOL)
    assert "result" not in practising.public_problem(p["id"])
    assert "model_solution" not in str(practising.public_problem(p["id"]))
    practising.conclude("s1", "solvedWithHints", "Needed R1 to see the sum.", rung="R1")
    assert practising.public_problem(p["id"])["result"]["model_solution"] == SOL


def test_thinking_trace_and_dismiss(practising):
    p = practising.pose("s1", "What is Var(q.k) for d_k = 64?", "recall", SOL)
    practising.add_thinking(p["id"], "each term is 1 so maybe 64?")
    practising.add_thinking(p["id"], "", hint=True)
    assert [t["hint"] for t in practising.problem(p["id"])["trace"]] == [False, True]
    d = practising.dismiss(p["id"])
    assert d["outcome"] == "dismissed" and d["retest"] is True
    with pytest.raises(LearnError, match="already concluded"):
        practising.add_thinking(p["id"], "late thought")


def test_conclude_validates(practising):
    with pytest.raises(LearnError, match="No active problem"):
        practising.conclude("s1", "solved", "fine")
    practising.pose("s1", "What is Var(q.k) for d_k = 64?", "recall", SOL)
    with pytest.raises(LearnError, match="outcome must be one of"):
        practising.conclude("s1", "dismissed", "learner only")
    with pytest.raises(LearnError, match="rung must be"):
        practising.conclude("s1", "solved", "ok fine", rung="R9")


def test_questions_refused_in_practice_and_problems_refused_in_lessons(practising, store):
    with pytest.raises(LearnError, match="practice session"):
        practising.ask("s1", "Which is it?", options=["a", "b"], correct=0, explanation="Because.")
    store.start_lesson("s2", "attention maths")
    with pytest.raises(LearnError, match="isn't a practice session"):
        store.pose("s2", "What is Var(q.k) for d_k = 64?", "recall", SOL)


def test_stop_abandons_open_problem(practising):
    p = practising.pose("s1", "What is Var(q.k) for d_k = 64?", "recall", SOL)
    practising.stop_lesson("s1")
    assert practising.problem(p["id"])["status"] == "abandoned"


# ---- core: entry, per-turn context, tools ----
from learnloop import core  # noqa: E402


def practice_message(topic):
    msg = ('[IMPORTANT: The user has invoked the "learnloop:practice" skill, indicating they want you to follow '
           "its instructions. The full skill content is loaded below.]\n\n---\nname: practice\n---\nMETHOD")
    if topic:
        msg += f"\n\nThe user has provided the following instruction alongside the skill invocation: {topic}"
    return msg


def test_practice_skill_is_generated_from_method():
    from pathlib import Path
    skill = (Path(core.__file__).parent / "skills/practice/SKILL.md").read_text(encoding="utf-8")
    assert skill == core.practice_skill_text(), "skills/practice/SKILL.md is stale: run python3 tools/build_skill.py"
    assert "name: practice" in skill and core.method_text("practice") in skill


def test_practice_doctrine_is_verbatim():
    from pathlib import Path
    root = Path(core.__file__).parent
    ours = core._strip_header((root / "method/practice.md").read_text(encoding="utf-8"))
    raw = (root / "docs/research/method-raw/practice/10-doctrine.md").read_text(encoding="utf-8")
    assert ours.strip() == core._strip_header(raw).strip()


def test_practice_start_picks_material(graph):
    ctx = core.turn_context(graph, "s1", practice_message("Dot product variance"))
    les = graph.active_lesson("s1")
    assert les["phase"] == "practice" and "Pose the first problem" in ctx
    assert "Variances add" in ctx and "→ Dot product variance" in ctx


def test_practice_without_topic_or_match(graph):
    assert "without a topic" in core.turn_context(graph, "s1", practice_message(""))
    assert graph.active_lesson("s1") is None
    ctx = core.turn_context(graph, "s2", practice_message("medieval poetry"))
    assert "free-form session" in ctx and graph.active_lesson("s2")["phase"] == "practice"


def test_problem_tool_text_and_cards(practising):
    out = core.tool_problem(practising, "s1", {"statement": "What is Var(q.k) for d_k = 64?", "mode": "recall",
                                               "modelSolution": SOL}, cards=False)
    assert out["show"].startswith("**Problem.**") and SOL not in str(out)
    ctx = core.turn_context(practising, "s1", "each term has variance 1 so 64")
    assert "Active problem" in ctx and "claimed answer" in ctx
    out = core.tool_conclude(practising, "s1", {"outcome": "solved", "verdict": "Both rules, in order.",
                                                "rung": "none", "missClass": "none"}, cards=False)
    assert SOL in out["show"] and "END your turn" in out["next"]
    p = practising.problems(practising.active_lesson("s1")["id"])[0]
    assert p["rung"] is None and p["miss_class"] is None


def test_pause_then_go_ahead(practising):
    core.tool_problem(practising, "s1", {"statement": "What is Var(q.k) for d_k = 64?", "mode": "recall",
                                         "modelSolution": SOL}, cards=True)
    core.tool_conclude(practising, "s1", {"outcome": "solved", "verdict": "Right."}, cards=True)
    ctx = core.turn_context(practising, "s1", "why did the cross terms vanish?")
    assert "Pause after problem" in ctx
    with pytest.raises(LearnError, match="Paused"):
        core.tool_problem(practising, "s1", {"statement": "A second problem here.", "mode": "recall",
                                             "modelSolution": SOL}, cards=True)
    ctx = core.turn_context(practising, "s1", "Next problem")
    assert "He asked for the next problem" in ctx
    assert core.tool_problem(practising, "s1", {"statement": "A second problem here.", "mode": "recall",
                                                "modelSolution": SOL}, cards=True)["show"].startswith("::learnloop-problem")


def test_go_ahead_in_own_words(practising):
    core.tool_problem(practising, "s1", {"statement": "What is Var(q.k) for d_k = 64?", "mode": "recall",
                                         "modelSolution": SOL}, cards=True)
    core.tool_conclude(practising, "s1", {"outcome": "solved", "verdict": "Right."}, cards=True)
    for words in ("next", "ok next one", "give me another one", "let's do the next problem"):
        assert core.GO_AHEAD.match(words), words
    for words in ("why is that next to it?", "what does the next step mean", "no"):
        assert not core.GO_AHEAD.match(words), words
    out = core.tool_problem(practising, "s1", {"statement": "A second problem here.", "mode": "recall",
                                               "modelSolution": SOL, "go_ahead": True}, cards=True)
    assert out["problem_id"]


def test_set_aside_context(practising):
    p = practising.pose("s1", "What is Var(q.k) for d_k = 64?", "recall", SOL)
    practising.dismiss(p["id"])
    ctx = core.turn_context(practising, "s1", core.SET_ASIDE_LINE)
    assert "set problem" in ctx and "dismissed" in ctx


def test_lesson_tools_refuse_in_practice(practising):
    with pytest.raises(LearnError, match="Practice doesn't add facts"):
        core.tool_record(practising, "s1", {"propositions": [{"name": "New fact", "statement": "A new statement."}]})
    assert core.tool_phase(practising, "s1", {"phase": "done"}, cards=False)["phase"] == "done"


def test_thinking_line(practising):
    p = practising.pose("s1", "What is Var(q.k) for d_k = 64?", "recall", SOL)
    assert core.thinking_line(practising.add_thinking(p["id"], "maybe 64"), hint=False) == "Thinking: maybe 64"
    assert core.thinking_line(practising.add_thinking(p["id"], "", hint=True), hint=True) == "I'm stuck: hint please."


def test_practice_command_on_messaging_platforms(graph):
    out = core.command(graph, "t1", "practice Dot product variance", platform="telegram")
    assert "Practice started" in out and "3 facts" in out
    ctx = core.turn_context(graph, "t1", "go")
    assert "call learn_method first" in ctx
    assert "material" in core.tool_method(graph, "t1", {})
    assert "/learnloop:practice" in core.command(graph, "d1", "practice softmax", platform="desktop")


def test_composer_messages_join_the_trace(practising):
    p = practising.pose("s1", "What is Var(q.k) for d_k = 64?", "recall", SOL)
    core.turn_context(practising, "s1", "each term has variance 1, so maybe 64?")
    core.turn_context(practising, "s1", "Thinking: from the card")  # the card's own line: already recorded
    core.turn_context(practising, "s1", "I'm stuck: hint please.")
    assert [t["text"] for t in practising.problem(p["id"])["trace"]] == ["each term has variance 1, so maybe 64?"]
    v = core.lesson_view(practising, "s1")["lesson"]["practice"]
    assert v["open_problem"]["id"] == p["id"] and v["open_problem"]["submissions"] == 1
