"""learnloop: structured lessons inside Hermes, with a knowledge graph shared across chats.

Inert until the user runs /study <topic> in a chat. Teaching method adapted from LearnHarness
(see NOTICE). Copyright (C) 2026 Hussein Al-Amodi. AGPL-3.0-only.
"""
from __future__ import annotations

import json
import logging
import threading

from . import core
from .store import LearnError, Store

log = logging.getLogger(__name__)
NAME = "learnloop"
TOOLSET = "learnloop"

_store: Store | None = None
_store_lock = threading.Lock()
_platforms: dict[str, str] = {}  # session_id -> platform seen by the hook (spike U3: tools see "local")


def get_store() -> Store:
    """One Store per process. plugin_db() is WAL + check_same_thread=False (spike U6)."""
    global _store
    with _store_lock:
        if _store is None:
            from plugins.plugin_storage import plugin_db
            _store = Store(plugin_db(NAME, "learnloop.db"))
        return _store


def _session_id(kwargs: dict) -> str:
    sid = kwargs.get("session_id") or ""
    if not sid:
        try:
            from gateway.session_context import get_session_env
            sid = get_session_env("HERMES_SESSION_ID", "")
        except Exception:  # noqa: BLE001 - outside a session
            sid = ""
    return sid


def _follow_compression(store: Store, session_id: str) -> None:
    """Compression gives the chat a new session id; carry an active lesson over to it."""
    if not session_id or store.active_lesson(session_id):
        return
    try:
        from hermes_state import SessionDB
        db = SessionDB(read_only=True)
        sid = session_id
        for _ in range(5):
            parent = (db.get_session(sid) or {}).get("parent_session_id")
            if not parent or (db.get_session(parent) or {}).get("end_reason") != "compression":
                return
            if store.active_lesson(parent):
                store.rebind_session(parent, session_id)
                return
            sid = parent
    except Exception as exc:  # noqa: BLE001 - best effort; never break a turn
        log.debug("learnloop: compression lookup failed: %s", exc)


def _tool(fn, needs_cards=False):
    def handler(args, **kwargs):
        sid = _session_id(kwargs)
        try:
            store = get_store()
            _follow_compression(store, sid)
            extra = {"cards": core.cards_enabled(store, _platforms.get(sid, ""))} if needs_cards else {}
            return json.dumps(fn(store, sid, args or {}, **extra), ensure_ascii=False)
        except LearnError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return handler


def register(ctx):
    handlers = {
        "learn_ask": _tool(core.tool_ask, needs_cards=True),
        "learn_grade": _tool(core.tool_grade),
        "learn_phase": _tool(core.tool_phase, needs_cards=True),
        "learn_method": _tool(core.tool_method),
        "learn_record": _tool(core.tool_record),
        "learn_recall": _tool(core.tool_recall),
    }
    for schema in core.schemas():
        ctx.register_tool(name=schema["name"], toolset=TOOLSET, schema=schema,
                          handler=handlers[schema["name"]], emoji="🎓")

    def pre_llm_call(session_id="", user_message="", platform="", **_):
        try:
            if platform:
                _platforms[session_id] = platform
            store = get_store()
            _follow_compression(store, session_id)
            text = core.turn_context(store, session_id, user_message or "")
        except Exception as exc:  # noqa: BLE001 - a plugin must never break the turn
            log.warning("learnloop: turn context failed: %s", exc)
            return None
        return {"context": text} if text else None

    ctx.register_hook("pre_llm_call", pre_llm_call)

    def transform_llm_output(response_text="", session_id="", **_):
        try:
            return core.dedupe_reply(get_store(), session_id, response_text)
        except Exception as exc:  # noqa: BLE001 - never break a reply
            log.warning("learnloop: reply clean-up failed: %s", exc)
            return None

    def on_session_delete(session_id="", **_):
        try:
            core.on_chat_deleted(get_store(), session_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("learnloop: ending a deleted chat's lesson failed: %s", exc)

    ctx.register_hook("transform_llm_output", transform_llm_output)
    ctx.register_hook("on_session_delete", on_session_delete)

    def study_command(raw_args, session_id="", **_):
        return core.command(get_store(), session_id or _session_id({}), raw_args)

    ctx.register_command("study", study_command,
                         description="Start or manage a learnloop lesson in this chat",
                         args_hint="<topic> | stop | status | map | graph | recall on|off")
