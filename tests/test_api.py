"""Backend routes the Desktop card calls (needs fastapi + httpx; skipped otherwise)."""
import importlib.util
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from learnloop import core  # noqa: E402

from .test_core import skill_message  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(store, monkeypatch):
    spec = importlib.util.spec_from_file_location("ll_api_under_test", ROOT / "dashboard/plugin_api.py")
    api = importlib.util.module_from_spec(spec)
    import sys
    sys.modules["ll_api_under_test"] = api  # as Hermes does before exec_module
    spec.loader.exec_module(api)
    pkg = api._plugin()
    monkeypatch.setattr(pkg, "get_store", lambda: store)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/plugins/learnloop")
    return TestClient(app)


def ask(store):
    core.turn_context(store, "s1", skill_message("attention maths"))
    return core.tool_ask(store, "s1", {"prompt": "Which returns a scalar?", "options": ["a+b", "a·b"],
                                       "correct": [1], "explanation": "The dot product sums products."},
                         cards=True)["question_id"]


def test_hello_marks_desktop_seen(client, store):
    assert client.post("/api/plugins/learnloop/hello").json() == {"ok": True}
    assert store.get_setting("desktop_ui") == "seen"


def test_get_then_submit(client, store):
    qid = ask(store)
    q = client.get(f"/api/plugins/learnloop/question/{qid}").json()
    assert q["options"] == ["a+b", "a·b"] and "result" not in q
    r = client.post(f"/api/plugins/learnloop/question/{qid}/submit",
                    json={"choices": [1], "confidence": 70, "thinking": "sum"}).json()
    assert r["question"]["result"]["verdict"] == "correct" and r["line"].startswith("B) a·b")


def test_errors_are_400(client, store):
    assert client.get("/api/plugins/learnloop/question/q_nope").status_code == 400
    qid = ask(store)
    assert client.post(f"/api/plugins/learnloop/question/{qid}/submit", json={}).status_code == 400


def test_lesson_lessons_graph_routes(client, store):
    assert client.get("/api/plugins/learnloop/lesson?session=s1").json() == {"lesson": None}
    ask(store)
    assert client.get("/api/plugins/learnloop/lesson?session=s1").json()["lesson"]["goal"] == "attention maths"
    assert client.get("/api/plugins/learnloop/lessons").json()["lessons"][0]["goal"] == "attention maths"
    assert client.get("/api/plugins/learnloop/graph").json() == {"propositions": [], "chains": []}


def test_problem_routes(client, store):
    store.start_practice("s1", "dot product variance", [])
    p = store.pose("s1", "What is Var(q.k) for d_k = 64?", "recall", "Sum of 64 unit variances: 64.")
    got = client.get(f"/api/plugins/learnloop/problem/{p['id']}").json()
    assert got["statement"].startswith("What is") and "result" not in got
    r = client.post(f"/api/plugins/learnloop/problem/{p['id']}/thinking", json={"text": "64?"}).json()
    assert r["line"] == "Thinking: 64?" and len(r["problem"]["trace"]) == 1
    r = client.post(f"/api/plugins/learnloop/problem/{p['id']}/dismiss").json()
    assert r["problem"]["result"]["outcome"] == "dismissed" and r["line"] == "I set this problem aside."
    assert client.post(f"/api/plugins/learnloop/problem/{p['id']}/dismiss").status_code == 400
    view = client.get("/api/plugins/learnloop/lesson?session=s1").json()["lesson"]
    assert view["phase"] == "practice" and view["practice"]["problems"][0]["label"] == "Set aside"
    assert client.get("/api/plugins/learnloop/lessons").json()["lessons"][0]["kind"] == "practice"
