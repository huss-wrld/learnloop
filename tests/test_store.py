import pytest

from learnloop.store import LearnError, parse_plan

from .conftest import ASSESS, PLAN


# ---- lessons ----
def test_start_lesson_enters_probe(store):
    les = store.start_lesson("s1", "understand scaled dot-product attention")
    assert les["phase"] == "probe" and les["session_id"] == "s1"


def test_one_active_lesson_per_chat(store):
    store.start_lesson("s1", "understand attention maths")
    with pytest.raises(LearnError, match="already has an active lesson"):
        store.start_lesson("s1", "something else")


def test_lessons_are_per_chat(store):
    store.start_lesson("s1", "understand attention maths")
    assert store.active_lesson("s2") is None


def test_stop_ends_lesson_and_abandons_open_question(store):
    store.start_lesson("s1", "understand attention maths")
    q = store.ask("s1", "What does a dot product return?", expected="A single number.")
    store.stop_lesson("s1")
    assert store.active_lesson("s1") is None
    assert store.question(q["id"])["status"] == "abandoned"


def test_rebind_after_compaction(store):
    store.start_lesson("s1", "understand attention maths")
    assert store.rebind_session("s1", "s2") == 1
    assert store.active_lesson("s2") and store.active_lesson("s1") is None


# ---- plan ----
def test_parse_plan_nodes_and_edges():
    nodes, edges = parse_plan(PLAN)
    assert nodes == {"dot": "Dot product", "scores": "Score matrix", "softmax": "Row softmax"}
    assert edges == [("dot", "scores"), ("scores", "softmax")]


def test_parse_plan_rejects_bad_slug_with_line_number():
    with pytest.raises(LearnError, match="line 2"):
        parse_plan("graph TD\n  Bad_Slug[x] --> b")


def test_plan_phase_requires_assessment(store):
    store.start_lesson("s1", "understand attention maths")
    with pytest.raises(LearnError, match="requires `assessment`"):
        store.set_phase("s1", "plan")
    les = store.set_phase("s1", "plan", assessment=ASSESS)
    assert les["phase"] == "plan" and "dot product" in les["assessment"]


def test_teach_requires_a_plan(store):
    store.start_lesson("s1", "understand attention maths")
    store.set_phase("s1", "plan", assessment=ASSESS)
    with pytest.raises(LearnError, match="needs a plan"):
        store.set_phase("s1", "teach")
    store.set_phase("s1", "plan", plan=PLAN)          # store the plan, still planning
    assert store.active_lesson("s1")["phase"] == "plan"
    assert store.set_phase("s1", "teach")["phase"] == "teach"


def test_no_questions_while_planning(store):
    store.start_lesson("s1", "understand attention maths")
    store.set_phase("s1", "plan", assessment=ASSESS, plan=PLAN)
    with pytest.raises(LearnError, match="while planning"):
        store.ask("s1", "Does this plan look right?", expected="Yes.")


def test_cannot_skip_probe(store):
    store.start_lesson("s1", "understand attention maths")
    with pytest.raises(LearnError, match="Cannot move from probe to teach"):
        store.set_phase("s1", "teach", plan=PLAN)


def test_replan_while_teaching(teaching):
    les = teaching.set_phase("s1", "teach", plan=PLAN + "\n  softmax --> goal[Goal]")
    assert "goal" in les["plan"] and les["phase"] == "teach"
    with pytest.raises(LearnError, match="Already in this phase"):
        teaching.set_phase("s1", "teach")


def test_a_lesson_cannot_turn_into_practice(store):
    # practice is its own session (/learnloop:practice), never a phase a lesson moves into
    store.start_lesson("s1", "understand attention maths")
    with pytest.raises(LearnError, match="Cannot move from probe to practice"):
        store.set_phase("s1", "practice")


def test_plan_position_and_map(teaching):
    for node in ("dot", "scores"):
        q = teaching.ask("s1", "Which is right here?", options=["a", "b"], correct=0,
                         explanation="Because a is right here.", qtype="check", node_id=node)
        teaching.grade(q["id"], answer="A", confidence=70)
    les = teaching.active_lesson("s1")
    st = teaching.plan_status(les["id"])
    assert st["visited"] == ["dot", "scores"] and st["current"] == "scores"
    m = teaching.plan_mermaid(les["id"])
    assert "class dot done" in m and "class scores current" in m


# ---- questions ----
def test_probe_questions_have_no_type_or_node(store):
    store.start_lesson("s1", "understand attention maths")
    with pytest.raises(LearnError, match="no `type`"):
        store.ask("s1", "What is a dot product?", expected="A number.", qtype="check")


def test_teach_questions_need_type_and_valid_node(teaching):
    with pytest.raises(LearnError, match="need `type`"):
        teaching.ask("s1", "What is a dot product?", expected="A number.")
    with pytest.raises(LearnError, match="node slugs"):
        teaching.ask("s1", "What is a dot product?", expected="A number.", qtype="check", node_id="nope")


def test_mc_needs_correct_and_explanation(store):
    store.start_lesson("s1", "understand attention maths")
    with pytest.raises(LearnError, match="`correct`"):
        store.ask("s1", "Which returns a scalar?", options=["a+b", "a·b"])
    with pytest.raises(LearnError, match="`explanation`"):
        store.ask("s1", "Which returns a scalar?", options=["a+b", "a·b"], correct=1)


def test_free_answer_needs_committed_expected(store):
    store.start_lesson("s1", "understand attention maths")
    with pytest.raises(LearnError, match="`expected`"):
        store.ask("s1", "Why divide by sqrt(d_k)?")


def test_single_open_question(store):
    store.start_lesson("s1", "understand attention maths")
    store.ask("s1", "What does a dot product return?", expected="A number.")
    with pytest.raises(LearnError, match="learn_grade first"):
        store.ask("s1", "What does softmax do to a row?", expected="Normalises it.")


def test_phase_change_blocked_by_open_question(store):
    store.start_lesson("s1", "understand attention maths")
    store.ask("s1", "What does a dot product return?", expected="A number.")
    with pytest.raises(LearnError, match="still open"):
        store.set_phase("s1", "plan", assessment=ASSESS)


# ---- answers and grading ----
def mc(store):
    store.start_lesson("s1", "understand attention maths")
    return store.ask("s1", "Which returns a scalar?", options=["a+b", "a·b", "a⊙b"], correct=1,
                     explanation="The dot product sums the products into one number.")


def test_mc_graded_from_key_not_model(store):
    q = mc(store)
    g = store.grade(q["id"], verdict="correct", answer="A", confidence=90, thinking="adding gives a number")
    assert g["verdict"] == "wrong" and g["confidence"] == 90 and g["answer"] == "A) a+b"


def test_card_submission_is_authoritative(store):
    q = mc(store)
    store.submit(q["id"], choices=[1], confidence=70, thinking="sum of products", reading_thinking="ok")
    g = store.grade(q["id"], answer="A", confidence=5)  # model's transcription ignored
    assert g["verdict"] == "correct" and g["confidence"] == 70 and g["reading_thinking"] == "ok"


def test_dont_know(store):
    q = mc(store)
    g = store.grade(q["id"], dont_know=True, confidence=90)
    assert g["verdict"] == "dont_know" and g["confidence"] is None


def test_multi_select(store):
    store.start_lesson("s1", "understand attention maths")
    q = store.ask("s1", "Which are scalars?", options=["a·b", "|a|", "a+b"], correct=[0, 1],
                  explanation="Dot products and norms are numbers.")
    assert store.grade(q["id"], answer="A, B")["verdict"] == "correct"


def test_free_answer_uses_model_verdict(store):
    store.start_lesson("s1", "understand attention maths")
    q = store.ask("s1", "Why divide by sqrt(d_k)?", expected="Keeps score variance at 1.")
    assert store.grade(q["id"], verdict="partial", answer="to keep it small")["verdict"] == "partial"


def test_confidence_is_percent(store):
    q = mc(store)
    with pytest.raises(LearnError, match="0-100"):
        store.grade(q["id"], answer="B", confidence=150)


def test_cannot_grade_twice(store):
    q = mc(store)
    store.grade(q["id"], answer="B")
    with pytest.raises(LearnError, match="already graded"):
        store.grade(q["id"], answer="B")


def test_recall_setting_defaults_off(store):
    assert store.get_setting("recall", "off") == "off"
    store.set_setting("recall", "on")
    assert store.get_setting("recall") == "on"
