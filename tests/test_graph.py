import pytest

from learnloop.store import LearnError


def P(name):
    return {"name": name, "statement": f"{name}: a full sentence statement for testing."}


def test_record_and_reuse_by_normalised_name(store):
    assert store.record("s1", [P("Dot product is a scalar")])["added_propositions"] == ["Dot product is a scalar"]
    r = store.record("s1", [P("dot product is a scalar!")])
    assert r["added_propositions"] == [] and r["reused_propositions"] == ["dot product is a scalar!"]


def test_chain_needs_known_names(store):
    with pytest.raises(LearnError, match="Unknown proposition"):
        store.record("s1", [], [{"premises": ["Nope"], "conclusion": "Also nope"}])


def test_learnharness_cycle_rejected_and_call_rolled_back(store):
    # The circular argument found in a real LearnHarness graph (8 Nov 2026).
    store.record("s1", [P("Value vectors"), P("Values don't affect weights")],
                 [{"premises": ["Value vectors"], "conclusion": "Values don't affect weights"}])
    with pytest.raises(LearnError, match="circular"):
        store.record("s1", [P("Brand new fact")],
                     [{"premises": ["Values don't affect weights"], "conclusion": "Value vectors"}])
    assert store.search("brand new fact") == []


def test_longer_cycle_rejected(store):
    store.record("s1", [P("Alpha fact"), P("Beta fact"), P("Gamma fact")],
                 [{"premises": ["Alpha fact"], "conclusion": "Beta fact"},
                  {"premises": ["Beta fact"], "conclusion": "Gamma fact"}])
    with pytest.raises(LearnError, match="circular"):
        store.record("s1", [], [{"premises": ["Gamma fact"], "conclusion": "Alpha fact"}])


def test_self_premise_rejected(store):
    store.record("s1", [P("Softmax rows sum to one")])
    with pytest.raises(LearnError, match="own premise"):
        store.record("s1", [], [{"premises": ["Softmax rows sum to one"], "conclusion": "Softmax rows sum to one"}])


def test_skip_cycles_mode_for_import(store):
    store.record("s1", [P("Value vectors"), P("Values don't affect weights")],
                 [{"premises": ["Value vectors"], "conclusion": "Values don't affect weights"}])
    r = store.record("s1", [], [{"premises": ["Values don't affect weights"], "conclusion": "Value vectors"}],
                     skip_cycles=True)
    assert r["skipped_circular"] == ["Value vectors"] and r["added_chains"] == 0


def test_duplicate_chain_is_ignored(store):
    chain = {"premises": ["Dot product is a scalar"], "conclusion": "Scores matrix is n by n"}
    store.record("s1", [P("Dot product is a scalar"), P("Scores matrix is n by n")], [chain])
    r = store.record("s1", [], [chain])
    assert r["added_chains"] == 0 and r["duplicate_chains"] == 1


def test_search_ranks_by_overlap_and_lists_premises(store):
    store.record("s1", [P("Softmax normalises rows"), P("Scores come from dot products")],
                 [{"premises": ["Scores come from dot products"], "conclusion": "Softmax normalises rows"}])
    hits = store.search("why does softmax normalise rows of scores")
    assert hits[0]["name"] == "Softmax normalises rows"
    assert hits[0]["premises"] == ["Scores come from dot products"]


def test_graph_export(store):
    store.record("s1", [P("Alpha fact"), P("Beta fact")], [{"premises": ["Alpha fact"], "conclusion": "Beta fact"}])
    g = store.graph()
    assert len(g["propositions"]) == 2 and len(g["chains"]) == 1 and len(g["chains"][0]["premises"]) == 1


# ---- graph view groups (11 Nov) ----
def test_graph_groups_by_lesson_or_origin(store):
    from learnloop import core
    from .test_core import skill_message
    core.turn_context(store, "s1", skill_message("attention maths"))
    store.record("s1", [{"name": "Dot product scalar", "statement": "A dot product returns one number."}])
    store.record("", [{"name": "Imported fact", "statement": "This one came from elsewhere.",
                       "origin": "LearnHarness: Scaled dot-product attention"}], source="learnharness")
    store.record("", [{"name": "Loose fact", "statement": "Recorded outside any lesson."}])
    g = {p["name"]: p for p in store.graph()["propositions"]}
    assert g["Dot product scalar"]["group_label"] == "attention maths" and g["Dot product scalar"]["session_id"] == "s1"
    assert g["Imported fact"]["group"] == "origin:LearnHarness: Scaled dot-product attention"
    assert g["Loose fact"]["group"] == "other"


def test_reimport_fills_missing_origin(store):
    store.record("", [{"name": "Imported fact", "statement": "This one came from elsewhere."}], source="learnharness")
    store.record("", [{"name": "Imported fact", "statement": "This one came from elsewhere.", "origin": "LH: X"}],
                 source="learnharness")
    assert store.graph()["propositions"][0]["group_label"] == "LH: X"


def test_old_database_gets_origin_column(tmp_path):
    import sqlite3
    from learnloop.store import Store
    conn = sqlite3.connect(tmp_path / "old.db")
    conn.execute("CREATE TABLE propositions(id TEXT PRIMARY KEY, key TEXT NOT NULL UNIQUE, name TEXT NOT NULL, "
                 "statement TEXT NOT NULL, lesson_id TEXT, source TEXT NOT NULL DEFAULT 'learnloop', "
                 "created_at TEXT NOT NULL)")
    conn.commit()
    Store(conn)
    assert "origin" in {r[1] for r in conn.execute("PRAGMA table_info(propositions)")}
