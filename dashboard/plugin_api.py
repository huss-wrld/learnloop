"""learnloop backend routes for its Desktop half (question card, lesson pane, Learn page).

Mounted by Hermes at /api/plugins/learnloop/. Copyright (C) 2026 Hussein Al-Amodi. AGPL-3.0-only.
"""
import importlib.util
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

_ROOT = Path(__file__).resolve().parents[1]
_NAME = "learnloop_dashboard_pkg"


def _plugin():
    """learnloop's own package, loaded once by path (this file is imported standalone, not as a package)."""
    mod = sys.modules.get(_NAME)
    if mod is None:
        spec = importlib.util.spec_from_file_location(_NAME, _ROOT / "__init__.py",
                                                      submodule_search_locations=[str(_ROOT)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[_NAME] = mod
        spec.loader.exec_module(mod)
    return mod


def _call(fn):
    pkg = _plugin()
    try:
        return fn(pkg, pkg.get_store())
    except Exception as exc:
        if type(exc).__name__ != "LearnError":  # by name: tests load the package twice
            raise
        raise HTTPException(status_code=400, detail=str(exc)) from exc


router = APIRouter()


class Submission(BaseModel):
    choices: Optional[list[int]] = None
    text: str = ""
    dont_know: bool = False
    confidence: Optional[int] = None
    thinking: str = ""
    reading_thinking: str = ""


@router.post("/hello")
def hello():
    """The Desktop half announces itself; learnloop only uses cards once it has (KI-7)."""
    return _call(lambda pkg, store: (store.set_setting("desktop_ui", "seen"), {"ok": True})[1])


@router.get("/question/{question_id}")
def get_question(question_id: str):
    return _call(lambda pkg, store: store.public_question(question_id))


@router.post("/question/{question_id}/submit")
def submit(question_id: str, body: Submission):
    def run(pkg, store):
        q = store.submit(question_id, choices=body.choices, text=body.text, dont_know=body.dont_know,
                         confidence=body.confidence, thinking=body.thinking,
                         reading_thinking=body.reading_thinking)
        return {"question": store.public_question(question_id), "line": pkg.core.card_answer_line(q)}
    return _call(run)
