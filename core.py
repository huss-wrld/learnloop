"""learnloop behaviour: tool handlers, the /study command and the per-turn hook.

Pure functions over a Store, so everything here is testable without Hermes.
Copyright (C) 2026 Hussein Al-Amodi. AGPL-3.0-only.
"""
from __future__ import annotations

import json
from pathlib import Path

from .store import CONFIDENCE_STOPS, LETTERS, LearnError, Store

METHOD_DIR = Path(__file__).parent / "method"
METHOD_BUDGET = 36_000  # spike U7: a 40k tool result arrived intact; keep headroom
RECALL_LIMIT = 6
PHASE_FILES = {"probe": ("shared.md", "probe.md"), "plan": ("shared.md", "teach.md"),
               "teach": ("shared.md", "teach.md")}


# ---------- method text ----------
def _strip_header(text: str) -> str:
    """Drop the leading attribution comment; the model doesn't need it."""
    if text.startswith("<!--"):
        text = text[text.index("-->") + 3:]
    return text.strip()


def method_text(phase: str) -> str:
    if phase not in PHASE_FILES:
        raise LearnError("No method for a finished lesson.")
    text = "\n\n---\n\n".join(_strip_header((METHOD_DIR / f).read_text(encoding="utf-8"))
                              for f in PHASE_FILES[phase])
    if len(text) > METHOD_BUDGET:
        raise RuntimeError(f"method for {phase} is {len(text)} chars, over the {METHOD_BUDGET} budget")
    return text


def reminder_text() -> str:
    return _strip_header((METHOD_DIR / "reminder.md").read_text(encoding="utf-8"))


# ---------- presentation ----------
def cards_enabled(store: Store, platform: str) -> bool:
    """Cards only where they render: a Desktop chat, with the Desktop half seen at least once
    (it pings on load), and not switched off by the user. Everyone else gets text mode."""
    return (platform == "desktop" and store.get_setting("desktop_ui") == "seen"
            and store.get_setting("cards", "on") == "on")


def question_show(q: dict, cards: bool) -> str:
    if cards:
        return f'::learnloop-question{{id="{q["id"]}"}}'
    lines = [f"**Question.** {q['prompt']}", ""]
    if q["options"]:
        lines += [f"{LETTERS[i]}) {opt}" for i, opt in enumerate(q["options"])]
        multi = len(q["correct"]) > 1
        lines += ["", f"Reply with the letter{'s' if multi else ''}"
                  f"{' (more than one is right)' if multi else ''}, "]
    else:
        lines += ["Reply with your answer in your own words, "]
    stops = "/".join(str(s) for s in CONFIDENCE_STOPS)
    lines[-1] += f"your confidence ({stops} %), and your thinking. Or say \"I don't know\"."
    return "\n".join(lines)


def map_show(store: Store, lesson_id: str, cards: bool) -> str:
    if cards:
        return f'::learnloop-map{{lesson="{lesson_id}"}}'
    mermaid = store.plan_mermaid(lesson_id)
    return f"```mermaid\n{mermaid}\n```" if mermaid else ""


# ---------- tools ----------
def tool_ask(store: Store, session_id: str, args: dict, cards: bool) -> dict:
    q = store.ask(session_id, args.get("prompt"), options=args.get("options"), correct=args.get("correct"),
                  explanation=args.get("explanation", ""), expected=args.get("expected", ""),
                  qtype=args.get("type"), node_id=args.get("node_id"))
    note = ("Card shown; the learner answers in it." if cards else
            "Text mode: the learner answers in chat. Don't reveal the explanation or answer yet.")
    return {"question_id": q["id"], "show": question_show(q, cards),
            "next": f"End your reply with `show` as its own final paragraph, then stop. {note} "
                    "When the answer arrives, call learn_grade first."}


def tool_grade(store: Store, session_id: str, args: dict) -> dict:
    les = store.require_lesson(session_id)
    open_q = store.open_question(les["id"])
    if open_q is None:
        raise LearnError("No open question to grade.")
    g = store.grade(open_q["id"], verdict=args.get("verdict"), answer=args.get("answer"),
                    dont_know=bool(args.get("dont_know")), confidence=args.get("confidence"),
                    thinking=args.get("thinking", ""), reading_thinking=args.get("reading_thinking", ""))
    out = {k: g[k] for k in ("verdict", "answer", "confidence", "thinking", "reading_thinking")}
    if g["options"]:
        out["correct"] = ", ".join(f"{LETTERS[i]}) {g['options'][i]}" for i in g["correct"])
        out["explanation"] = g["explanation"]
    else:
        out["expected"] = g["expected"]
    confident_miss = g["verdict"] in ("wrong", "partial") and (g["confidence"] or 0) >= 70
    out["next"] = (
        "Confident miss: a firmly held wrong model. Name the wrong model from the answer and thinking, "
        "repair it, re-check before moving on." if confident_miss else
        "Read the thinking, not only the verdict. If it landed, record it with learn_record and continue; "
        "if not, repair and re-check.")
    return out


def tool_phase(store: Store, session_id: str, args: dict, cards: bool) -> dict:
    before = store.require_lesson(session_id)["phase"]
    les = store.set_phase(session_id, args.get("phase"), plan=args.get("plan"),
                          assessment=args.get("assessment"))
    out = {"phase": les["phase"]}
    if les["phase"] == "done":
        out["next"] = "Lesson finished. Summarise what he now holds (learn_record anything unrecorded)."
        return out
    if les["plan"]:
        out["map"] = map_show(store, les["id"], cards)
    if les["phase"] == "plan" and not les["plan"]:
        out["next"] = "Write the plan now and store it with learn_phase(phase='plan', plan=...)."
    elif les["phase"] == "plan":
        out["next"] = ("Present the plan: end your message with `map` as its own paragraph, ask if it fits, "
                       "and wait. When he agrees, call learn_phase(phase='teach').")
    elif before == "plan":
        out["next"] = "Teach the first node."
    else:
        out["next"] = "Plan revised; carry on without re-presenting it."
    if PHASE_FILES[les["phase"]] != PHASE_FILES[before]:
        out["method"] = method_text(les["phase"])  # only when the method changes (probe -> plan)
    return out


def tool_method(store: Store, session_id: str, args: dict) -> dict:
    les = store.require_lesson(session_id)
    return {"phase": les["phase"], "goal": les["goal"], "method": method_text(les["phase"])}


def tool_record(store: Store, session_id: str, args: dict) -> dict:
    store.require_lesson(session_id)
    return store.record(session_id, args.get("propositions"), args.get("chains"))


def tool_recall(store: Store, session_id: str, args: dict) -> dict:
    if store.active_lesson(session_id) is None and store.get_setting("recall", "off") != "on":
        raise LearnError("learnloop recall is off outside lessons. The user can turn it on with /study recall on.")
    hits = store.search(args.get("query", ""), limit=min(int(args.get("limit") or RECALL_LIMIT), 20))
    return {"facts": [{"name": h["name"], "statement": h["statement"], "from": h["premises"]} for h in hits]}


# ---------- per-turn hook ----------
def turn_context(store: Store, session_id: str, user_message: str) -> str | None:
    les = store.active_lesson(session_id)
    if les:
        open_q = store.open_question(les["id"])
        state = [f"[learnloop] Active lesson in this chat. Goal: {les['goal']}. Phase: {les['phase']}."]
        if les["phase"] == "probe" and not store.answers(les["id"]) and open_q is None:
            state.append("The lesson just started: call learn_method to load the probe method, then begin.")
        if open_q:
            state.append(f"Open question {open_q['id']}: {open_q['prompt'][:300]}"
                         + (" (the learner submitted it in the card: call learn_grade now)"
                            if open_q["submission"] else ""))
        if les["plan"]:
            st = store.plan_status(les["id"])
            nxt = [n for n in st["nodes"] if n not in st["visited"]][:3]
            state.append(f"Plan position: current={st['current'] or 'none'}; visited={len(st['visited'])}/"
                         f"{len(st['nodes'])}; next unvisited: {', '.join(nxt) or 'none'}.")
        return "\n".join(state) + "\n\n" + reminder_text()
    if store.get_setting("recall", "off") == "on":
        hits = store.search(user_message or "", limit=RECALL_LIMIT)
        if hits:
            facts = "\n".join(f"- {h['name']}: {h['statement']}" for h in hits)
            return ("[learnloop] The user has learned these (from their learnloop knowledge graph). Use them "
                    "only if relevant: build on what they hold, in their terms. If you use any, end your "
                    "reply with the line: _used learnloop knowledge_\n" + facts)
    return None


# ---------- /study command ----------
HELP = """**learnloop**: structured lessons that stay in this chat only.

- `/study <topic>`: start a lesson in this chat (probe → plan → teach)
- `/study stop`: end it
- `/study status`: this chat's lesson and your graph size
- `/study map`: the lesson plan with your position
- `/study graph [words]`: what you've learned (search with words)
- `/study recall on|off`: let other chats use what you've learned (off by default)
- `/study cards on|off`: answer cards in Hermes Desktop (on by default)
- `/study import <LearnHarness data dir>`: import a LearnHarness knowledge graph"""


def command(store: Store, session_id: str, raw: str) -> str:
    raw = (raw or "").strip()
    word, _, rest = raw.partition(" ")
    word, rest = word.lower(), rest.strip()
    try:
        if not raw or word in ("help", "-h", "--help"):
            return HELP
        if word == "stop" and not rest:
            les = store.stop_lesson(session_id)
            return f"Lesson ended: *{les['goal']}*. What you learned stays in your graph."
        if word == "status" and not rest:
            return _status(store, session_id)
        if word == "map" and not rest:
            les = store.require_lesson(session_id)
            shown = map_show(store, les["id"], cards=False)
            return shown or "No plan yet: the lesson is still probing what you know."
        if word == "graph":
            return _graph(store, rest)
        if word in ("recall", "cards") and rest in ("on", "off"):
            store.set_setting(word, rest)
            return {("recall", "on"): "Recall **on**: other chats may use up to 6 facts you've learned, and "
                                      "will say so with *used learnloop knowledge*.",
                    ("recall", "off"): "Recall **off**: learnloop stays out of chats without a lesson.",
                    ("cards", "on"): "Answer cards **on** (Hermes Desktop with the learnloop Desktop part enabled).",
                    ("cards", "off"): "Answer cards **off**: questions appear as text."}[(word, rest)]
        if word == "import" and rest:
            return _import(store, Path(rest).expanduser())
        les = store.start_lesson(session_id, raw)
        return (f"Lesson started in this chat: *{les['goal']}*.\n\nFirst I'll find out what you already know, "
                "then propose a plan. Send **go** to begin. `/study stop` ends it anytime.")
    except LearnError as e:
        return str(e)


def _status(store: Store, session_id: str) -> str:
    s = store.stats()
    lines = []
    les = store.active_lesson(session_id)
    if les:
        answered = store.answers(les["id"])
        lines.append(f"**Lesson:** {les['goal']}  \n**Phase:** {les['phase']}  \n**Questions answered:** "
                     f"{len(answered)} ({sum(a['verdict'] == 'correct' for a in answered)} correct)")
        if les["plan"]:
            st = store.plan_status(les["id"])
            lines.append(f"**Plan:** {len(st['visited'])}/{len(st['nodes'])} steps reached")
    else:
        lines.append("No lesson in this chat. Start one with `/study <topic>`.")
    lines.append(f"**Your graph:** {s['propositions']} facts, {s['chains']} reasoning links, "
                 f"{s['lessons']} lessons. Recall in other chats: **{store.get_setting('recall', 'off')}**.")
    return "\n\n".join(lines)


def _graph(store: Store, words: str) -> str:
    props = store.search(words, limit=10) if words else store.recent_props(10)
    if not props:
        return "Nothing matches." if words else "Your graph is empty. Start a lesson with `/study <topic>`."
    head = f"Facts matching *{words}*:" if words else "Your 10 most recent facts:"
    return head + "\n\n" + "\n".join(f"- **{p['name']}**: {p['statement']}" for p in props)


def _import(store: Store, path: Path) -> str:
    """Import a LearnHarness graph (data dir, or its graph/ folder). Circular chains are skipped."""
    folder = path / "graph" if (path / "graph" / "nodes.jsonl").exists() else path
    nodes_file, chains_file = folder / "nodes.jsonl", folder / "chains.jsonl"
    if not nodes_file.exists():
        raise LearnError(f"No nodes.jsonl in {folder}. Point at LearnHarness's data folder, "
                         "e.g. ~/.config/LearnHarness/data")

    def rows(f):
        return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()] \
            if f.exists() else []

    nodes = rows(nodes_file)
    names = {n["id"]: n["name"] for n in nodes}
    props = [{"name": n["name"], "statement": n["statement"]} for n in nodes]
    chains = [{"premises": [names[p] for p in c["premises"]], "conclusion": names[c["conclusion"]]}
              for c in rows(chains_file)
              if c.get("conclusion") in names and c.get("premises") and all(p in names for p in c["premises"])]
    r = store.record("", props, chains, source="learnharness", skip_cycles=True)
    msg = (f"Imported from LearnHarness: {len(r['added_propositions'])} new facts "
           f"({len(r['reused_propositions'])} already known), {r['added_chains']} reasoning links.")
    if r["skipped_circular"]:
        msg += (f"\n\nSkipped {len(r['skipped_circular'])} circular link(s), where a fact ends up supporting "
                "itself: " + ", ".join(f"*{c}*" for c in r["skipped_circular"]))
    return msg


# ---------- tool schemas (kept short: they're listed in every session that loads the toolset) ----------
def schemas() -> list[dict]:
    obj, s, arr = "object", "string", "array"
    return [
        {"name": "learn_ask", "description":
            "learnloop lesson only: ask the learner ONE graded question (multiple choice with options+correct+"
            "explanation, or free recall with expected). Write explanation/expected BEFORE choosing correct. "
            "While teaching, also give type and node_id. Returns `show`: end your reply with it and stop.",
         "parameters": {"type": obj, "required": ["prompt"], "properties": {
             "prompt": {"type": s}, "options": {"type": arr, "items": {"type": s}},
             "explanation": {"type": s, "description": "MC: why the right option is right; shown after answering"},
             "correct": {"type": arr, "items": {"type": "integer"}, "description": "MC: 0-based right option(s)"},
             "expected": {"type": s, "description": "Free recall: your committed answer with reasoning"},
             "type": {"type": s, "enum": ["predict", "check"]}, "node_id": {"type": s}}}},
        {"name": "learn_grade", "description":
            "learnloop lesson only: record the learner's answer to the open question. Call first when an "
            "answer arrives. MC is graded automatically; give verdict for free recall. Text mode: pass what "
            "they wrote.",
         "parameters": {"type": obj, "properties": {
             "verdict": {"type": s, "enum": ["correct", "partial", "wrong"]},
             "answer": {"type": s, "description": "Their option letter(s) or words"},
             "dont_know": {"type": "boolean"}, "confidence": {"type": "integer", "description": "0-100 %"},
             "thinking": {"type": s}, "reading_thinking": {"type": s}}}},
        {"name": "learn_phase", "description":
            "learnloop lesson only: move phase probe→plan→teach→done, or store/revise the plan. plan needs "
            "assessment; the plan is a Mermaid 'graph TD' of slug[title] nodes and a --> b edges. Returns the "
            "phase's method: follow it.",
         "parameters": {"type": obj, "required": ["phase"], "properties": {
             "phase": {"type": s, "enum": ["plan", "teach", "done"]}, "plan": {"type": s},
             "assessment": {"type": obj, "properties": {"summary": {"type": s}, "strands": {"type": arr, "items": {
                 "type": obj, "properties": {"strand": {"type": s}, "assessment": {"type": s}}}}}}}}},
        {"name": "learn_method", "description":
            "learnloop lesson only: reload the full teaching method for the current phase (at lesson start, "
            "or when it's no longer in the conversation).",
         "parameters": {"type": obj, "properties": {}}},
        {"name": "learn_record", "description":
            "learnloop lesson only: save what the learner now holds: propositions (short name + full-sentence "
            "statement) and chains (premise names → conclusion name). Circular chains are rejected.",
         "parameters": {"type": obj, "properties": {
             "propositions": {"type": arr, "items": {"type": obj, "properties": {
                 "name": {"type": s}, "statement": {"type": s}}}},
             "chains": {"type": arr, "items": {"type": obj, "properties": {
                 "premises": {"type": arr, "items": {"type": s}}, "conclusion": {"type": s}}}}}}},
        {"name": "learn_recall", "description":
            "Search what the user has learned with learnloop. Only during a lesson, or when the user enabled "
            "recall.",
         "parameters": {"type": obj, "required": ["query"], "properties": {
             "query": {"type": s}, "limit": {"type": "integer"}}}},
    ]
