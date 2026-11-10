"""learnloop storage: lessons, questions, settings and the learner's knowledge graph.

Pure stdlib on purpose (no Hermes imports) so the tests run without Hermes.
Copyright (C) 2026 Hussein Al-Amodi. AGPL-3.0-only.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

PHASES = ("probe", "plan", "teach", "done")
TRANSITIONS = {"probe": {"plan", "done"}, "plan": {"teach", "done"}, "teach": {"done"}, "done": set()}
VERDICTS = ("correct", "partial", "wrong")
QTYPES = ("predict", "check")
CONFIDENCE_STOPS = (0, 30, 50, 70, 90, 100)  # LearnHarness's slider stops
LETTERS = "ABCDEFGH"
SLUG = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
_NODE = r"([A-Za-z0-9_-]+)(?:\s*\[\s*\"?(.*?)\"?\s*\])?"
_EDGE = re.compile(rf"^{_NODE}\s*-->\s*{_NODE}$")
_LONE = re.compile(rf"^{_NODE}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons(
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL, goal TEXT NOT NULL,
  phase TEXT NOT NULL DEFAULT 'probe', plan TEXT NOT NULL DEFAULT '',
  assessment TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS lessons_session ON lessons(session_id);
CREATE TABLE IF NOT EXISTS questions(
  id TEXT PRIMARY KEY, lesson_id TEXT NOT NULL REFERENCES lessons(id),
  phase TEXT NOT NULL, qtype TEXT, node_id TEXT,
  prompt TEXT NOT NULL, options TEXT NOT NULL DEFAULT '[]', correct TEXT NOT NULL DEFAULT '[]',
  explanation TEXT NOT NULL DEFAULT '', expected TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open', submission TEXT,
  answer TEXT, dont_know INTEGER NOT NULL DEFAULT 0, confidence INTEGER,
  thinking TEXT, reading_thinking TEXT, verdict TEXT,
  created_at TEXT NOT NULL, answered_at TEXT);
CREATE INDEX IF NOT EXISTS questions_lesson ON questions(lesson_id, status);
CREATE TABLE IF NOT EXISTS propositions(
  id TEXT PRIMARY KEY, key TEXT NOT NULL UNIQUE, name TEXT NOT NULL, statement TEXT NOT NULL,
  lesson_id TEXT, source TEXT NOT NULL DEFAULT 'learnloop', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chains(
  id TEXT PRIMARY KEY, conclusion TEXT NOT NULL REFERENCES propositions(id),
  lesson_id TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chain_premises(
  chain_id TEXT NOT NULL REFERENCES chains(id), premise TEXT NOT NULL REFERENCES propositions(id),
  PRIMARY KEY(chain_id, premise));
CREATE INDEX IF NOT EXISTS chain_premises_premise ON chain_premises(premise);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class LearnError(ValueError):
    """Invalid request. The message goes back to the model or user verbatim, so keep it actionable."""


def grade_first(q: dict) -> LearnError:
    return LearnError(f"Question {q['id']} is still open: the learner's last message answers it. "
                      "Call learn_grade first, then retry this call.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def key_of(name: str) -> str:
    """Normalise a proposition name: 'Dot product is a scalar!' == 'dot product is a scalar'."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(name).lower())).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in key_of(text).split() if len(t) > 2}


def parse_plan(mermaid: str) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Parse the plan subset: `graph TD`, `slug[title]` nodes and `a --> b` requires-edges.

    Returns ({slug: title}, [(from, to)]). Raises LearnError with line-numbered messages.
    """
    lines = [ln.strip() for ln in (mermaid or "").strip().splitlines()]
    if not lines or not re.match(r"^(graph|flowchart)\s+(TD|TB)$", lines[0]):
        raise LearnError("plan must start with 'graph TD' (Mermaid).")
    nodes: dict[str, str] = {}
    edges: list[tuple[str, str]] = []
    errors = []

    def add(slug, title, no):
        if not SLUG.match(slug):
            errors.append(f"line {no}: node id `{slug}` must be a lowercase slug (a-z, 0-9, - or _).")
            return
        if title or slug not in nodes:
            nodes[slug] = title or nodes.get(slug) or slug

    for no, line in enumerate(lines[1:], start=2):
        if not line or line.startswith("%%"):
            continue
        m = _EDGE.match(line)
        if m:
            a, at, b, bt = m.groups()
            add(a, at, no)
            add(b, bt, no)
            edges.append((a, b))
            continue
        m = _LONE.match(line)
        if m:
            add(m.group(1), m.group(2), no)
            continue
        errors.append(f"line {no}: can't parse `{line}`; use `slug[title]` or `a --> b`.")
    if errors:
        raise LearnError("Plan rejected:\n" + "\n".join(errors))
    if not nodes:
        raise LearnError("plan has no nodes.")
    return nodes, edges


class Store:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    @contextmanager
    def _tx(self):
        """Savepoint transaction: works whether the connection autocommits or not."""
        with self.lock:
            self.conn.execute("SAVEPOINT ll")
            try:
                yield
            except BaseException:
                self.conn.execute("ROLLBACK TO ll")
                self.conn.execute("RELEASE ll")
                raise
            self.conn.execute("RELEASE ll")
            if self.conn.in_transaction:
                self.conn.commit()

    def _one(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args).fetchone()

    def _all(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    # ---------- settings ----------
    def get_setting(self, key: str, default: str = "") -> str:
        row = self._one("SELECT value FROM settings WHERE key=?", (key,))
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._tx():
            self.conn.execute("INSERT INTO settings(key, value) VALUES (?,?) "
                              "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    # ---------- lessons ----------
    def lesson(self, lesson_id: str) -> dict:
        row = self._one("SELECT * FROM lessons WHERE id=?", (lesson_id,))
        if row is None:
            raise LearnError(f"Unknown lesson id {lesson_id}.")
        return dict(row)

    def active_lesson(self, session_id: str) -> dict | None:
        if not session_id:
            return None
        row = self._one("SELECT * FROM lessons WHERE session_id=? AND phase!='done' "
                        "ORDER BY created_at DESC, rowid DESC LIMIT 1", (session_id,))
        return dict(row) if row else None

    def require_lesson(self, session_id: str) -> dict:
        les = self.active_lesson(session_id)
        if les is None:
            raise LearnError("No active lesson in this chat. The user starts one with /learnloop <topic>.")
        return les

    def start_lesson(self, session_id: str, goal: str) -> dict:
        goal = (goal or "").strip()
        if not session_id:
            raise LearnError("No session id: a lesson can only start inside a chat.")
        if len(goal) < 4:
            raise LearnError("Say what you want to learn, e.g. /learnloop why attention divides by sqrt(d_k).")
        with self._tx():
            if self.active_lesson(session_id):
                raise LearnError("This chat already has an active lesson. End it with /learnloop stop first.")
            lesson_id, t = _new_id("l"), _now()
            self.conn.execute("INSERT INTO lessons(id, session_id, goal, phase, created_at, updated_at) "
                              "VALUES (?,?,?,?,?,?)", (lesson_id, session_id, goal, "probe", t, t))
        return self.lesson(lesson_id)

    def stop_lesson(self, session_id: str) -> dict:
        les = self.require_lesson(session_id)
        with self._tx():
            self.conn.execute("UPDATE questions SET status='abandoned' WHERE lesson_id=? AND status='open'",
                              (les["id"],))
            self.conn.execute("UPDATE lessons SET phase='done', updated_at=? WHERE id=?", (_now(), les["id"]))
        return self.lesson(les["id"])

    def set_phase(self, session_id, phase, plan=None, assessment=None) -> dict:
        """probe -> plan (needs `assessment`) -> teach (needs a stored or given plan) -> done.
        Calling with the CURRENT phase plus `plan` stores or revises the plan (plan and teach only)."""
        les = self.require_lesson(session_id)
        if phase not in PHASES:
            raise LearnError(f"phase must be one of {', '.join(PHASES)}.")
        plan = (plan or "").strip()
        same = phase == les["phase"]
        if same and not (phase in ("plan", "teach") and plan):
            raise LearnError("Already in this phase. To store or revise the plan, call learn_phase with the "
                             "current phase and `plan`.")
        if not same and phase not in TRANSITIONS[les["phase"]]:
            allowed = ", ".join(sorted(TRANSITIONS[les["phase"]])) or "none"
            raise LearnError(f"Cannot move from {les['phase']} to {phase}. Allowed: {allowed}.")
        assessment_json = les["assessment"]
        if phase == "plan" and les["phase"] == "probe":
            assessment_json = json.dumps(_validate_assessment(assessment), ensure_ascii=False)
        if plan:
            parse_plan(plan)
        if phase == "teach" and not (plan or les["plan"]):
            raise LearnError("Teaching needs a plan: store it with learn_phase(phase='plan', plan=...) "
                             "and present it first.")
        open_q = None if same else self.open_question(les["id"])
        if open_q:
            raise grade_first(open_q)
        with self._tx():
            self.conn.execute(
                "UPDATE lessons SET phase=?, plan=CASE WHEN ?='' THEN plan ELSE ? END, assessment=?, "
                "updated_at=? WHERE id=?", (phase, plan, plan, assessment_json, _now(), les["id"]))
        return self.lesson(les["id"])

    def rebind_session(self, old_session_id: str, new_session_id: str) -> int:
        with self._tx():
            cur = self.conn.execute("UPDATE lessons SET session_id=? WHERE session_id=?",
                                    (new_session_id, old_session_id))
        return cur.rowcount

    def plan_status(self, lesson_id: str) -> dict:
        """{nodes, edges, visited (ordered), current}. Position = the latest tagged teach question."""
        les = self.lesson(lesson_id)
        if not les["plan"]:
            return {"nodes": {}, "edges": [], "visited": [], "current": None}
        nodes, edges = parse_plan(les["plan"])
        tagged = [r[0] for r in self._all(
            "SELECT node_id FROM questions WHERE lesson_id=? AND node_id IS NOT NULL ORDER BY created_at, rowid",
            (lesson_id,))]
        visited = list(dict.fromkeys(n for n in tagged if n in nodes))
        return {"nodes": nodes, "edges": edges, "visited": visited, "current": visited[-1] if visited else None}

    def plan_mermaid(self, lesson_id: str) -> str:
        """The plan as Mermaid with done/current/next styling for the map card."""
        st = self.plan_status(lesson_id)
        if not st["nodes"]:
            return ""
        out = ["graph TD"]
        for slug, title in st["nodes"].items():
            out.append(f'  {slug}["{title.replace(chr(34), "")}"]')
        out += [f"  {a} --> {b}" for a, b in st["edges"]]
        out += ["  classDef done fill:#2e7d3233,stroke:#2e7d32",
                "  classDef current fill:#f9a82566,stroke:#f9a825,stroke-width:3px"]
        done = [n for n in st["visited"] if n != st["current"]]
        if done:
            out.append(f"  class {','.join(done)} done")
        if st["current"]:
            out.append(f"  class {st['current']} current")
        return "\n".join(out)

    # ---------- questions ----------
    @staticmethod
    def _q(row) -> dict:
        d = dict(row)
        for k in ("options", "correct"):
            d[k] = json.loads(d[k] or "[]")
        d["submission"] = json.loads(d["submission"]) if d.get("submission") else None
        return d

    def question(self, question_id: str) -> dict:
        row = self._one("SELECT * FROM questions WHERE id=?", (question_id,))
        if row is None:
            raise LearnError(f"Unknown question id {question_id}.")
        return self._q(row)

    def open_question(self, lesson_id: str) -> dict | None:
        row = self._one("SELECT * FROM questions WHERE lesson_id=? AND status='open'", (lesson_id,))
        return self._q(row) if row else None

    def ask(self, session_id, prompt, options=None, correct=None, explanation="", expected="",
            qtype=None, node_id=None) -> dict:
        les = self.require_lesson(session_id)
        prompt = (prompt or "").strip()
        if len(prompt) < 5:
            raise LearnError("prompt is empty or too short.")
        if les["phase"] == "probe":
            if qtype or node_id:
                raise LearnError("Probe questions take no `type` or `node_id`; there is no plan yet.")
        elif les["phase"] == "teach":
            if qtype not in QTYPES:
                raise LearnError("Teach questions need `type`: 'predict' (before teaching a step) or "
                                 "'check' (after it).")
            nodes = self.plan_status(les["id"])["nodes"]
            if node_id not in nodes:
                raise LearnError(f"`node_id` must be one of the plan's node slugs: {', '.join(nodes)}.")
        elif les["phase"] == "plan":
            raise LearnError("No graded questions while planning: present the plan, wait for the learner to "
                             "confirm it, then call learn_phase(phase='teach').")
        else:
            raise LearnError("The lesson is finished.")
        opts = [str(o).strip() for o in (options or []) if str(o).strip()]
        if opts:
            if not 2 <= len(opts) <= len(LETTERS):
                raise LearnError(f"Multiple choice needs 2 to {len(LETTERS)} options.")
            idx = correct if isinstance(correct, list) else [correct]
            try:
                idx = sorted({int(i) for i in idx})
            except (TypeError, ValueError):
                raise LearnError("Multiple choice needs `correct`: the 0-based index (or list of indices) "
                                 "of the right option(s).") from None
            if not idx or any(not 0 <= i < len(opts) for i in idx):
                raise LearnError("`correct` must hold valid 0-based option indices.")
            if len((explanation or "").strip()) < 10:
                raise LearnError("Multiple choice needs `explanation` (why the correct option is correct; "
                                 "shown to the learner after they answer). Write it before choosing `correct`.")
            expected = ""
        else:
            idx = []
            if len((expected or "").strip()) < 3:
                raise LearnError("Free-answer questions need `expected`: your committed answer with its "
                                 "reasoning, written before the learner answers.")
        open_q = self.open_question(les["id"])
        if open_q:
            raise grade_first(open_q)
        question_id = _new_id("q")
        with self._tx():
            self.conn.execute(
                "INSERT INTO questions(id, lesson_id, phase, qtype, node_id, prompt, options, correct, "
                "explanation, expected, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (question_id, les["id"], les["phase"], qtype, node_id, prompt, json.dumps(opts),
                 json.dumps(idx), (explanation or "").strip(), (expected or "").strip(), _now()))
        return self.question(question_id)

    def submit(self, question_id, choices=None, text="", dont_know=False, confidence=None,
               thinking="", reading_thinking="") -> dict:
        """Store the learner's own answer (from the Desktop card). learn_grade reads it later."""
        q = self.question(question_id)
        if q["status"] != "open":
            raise LearnError("This question was already answered.")
        sub = _validate_answer(q, choices, text, dont_know, confidence)
        sub.update(thinking=(thinking or "").strip()[:8000], reading_thinking=(reading_thinking or "").strip()[:8000])
        with self._tx():
            self.conn.execute("UPDATE questions SET submission=? WHERE id=?",
                              (json.dumps(sub, ensure_ascii=False), question_id))
        return self.question(question_id)

    def grade(self, question_id, verdict=None, answer=None, dont_know=False, confidence=None,
              thinking="", reading_thinking="") -> dict:
        """Grade the open question. A card submission is authoritative; text-mode args are the fallback.
        Multiple choice is graded from the answer key; free answers take the model's verdict."""
        q = self.question(question_id)
        if q["status"] != "open":
            raise LearnError(f"Question {question_id} is already graded.")
        sub = q["submission"]
        if sub is None:
            choices = None
            if q["options"]:
                choices = [LETTERS.index(c) for c in re.findall(r"\b([A-H])\b", (answer or "").upper())
                           if LETTERS.index(c) < len(q["options"])]
                if not choices and not dont_know:
                    raise LearnError("Pass the learner's option letter(s) in `answer`, e.g. 'B' or 'A, C'.")
            sub = _validate_answer(q, choices, answer or "", dont_know, confidence)
            sub.update(thinking=(thinking or "").strip(), reading_thinking=(reading_thinking or "").strip())
        if sub["dont_know"]:
            verdict = "dont_know"
        elif q["options"]:
            verdict = "correct" if sorted(sub["choices"]) == q["correct"] else "wrong"
        elif verdict not in VERDICTS:
            raise LearnError(f"Free answers need `verdict`: one of {', '.join(VERDICTS)}.")
        shown = (", ".join(f"{LETTERS[i]}) {q['options'][i]}" for i in sub["choices"])
                 if q["options"] else sub["text"])
        with self._tx():
            self.conn.execute(
                "UPDATE questions SET status='answered', answer=?, dont_know=?, confidence=?, thinking=?, "
                "reading_thinking=?, verdict=?, answered_at=? WHERE id=?",
                (shown, int(sub["dont_know"]), sub["confidence"], sub["thinking"], sub["reading_thinking"],
                 verdict, _now(), question_id))
        return self.question(question_id)

    def answers(self, lesson_id: str) -> list[dict]:
        return [self._q(r) for r in self._all(
            "SELECT * FROM questions WHERE lesson_id=? AND status='answered' ORDER BY answered_at, rowid",
            (lesson_id,))]

    # ---------- knowledge graph ----------
    def _prop_id(self, key: str) -> str | None:
        row = self._one("SELECT id FROM propositions WHERE key=?", (key,))
        return row[0] if row else None

    def _resolve(self, name) -> str:
        pid = self._prop_id(key_of(name or ""))
        if pid is None:
            raise LearnError(f"Unknown proposition '{name}'. Add it under 'propositions' in the same call, "
                             "or use its existing name exactly.")
        return pid

    def _reaches(self, start: str, targets: set[str]) -> bool:
        """True if `start` already supports (directly or transitively) any of `targets`."""
        seen, frontier = {start}, [start]
        while frontier:
            node = frontier.pop()
            for (nxt,) in self.conn.execute(
                    "SELECT c.conclusion FROM chain_premises p JOIN chains c ON c.id=p.chain_id WHERE p.premise=?",
                    (node,)).fetchall():
                if nxt in targets:
                    return True
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append(nxt)
        return False

    def _chain_exists(self, conclusion: str, premises: set[str]) -> bool:
        for (chain_id,) in self.conn.execute("SELECT id FROM chains WHERE conclusion=?", (conclusion,)).fetchall():
            existing = {r[0] for r in self.conn.execute(
                "SELECT premise FROM chain_premises WHERE chain_id=?", (chain_id,)).fetchall()}
            if existing == premises:
                return True
        return False

    def record(self, session_id, propositions=None, chains=None, source="learnloop", skip_cycles=False) -> dict:
        les = self.active_lesson(session_id)
        lesson_id = les["id"] if les else None
        propositions, chains = list(propositions or []), list(chains or [])
        if not propositions and not chains:
            raise LearnError("Nothing to record: pass propositions and/or chains.")
        added, reused, added_chains, dup, cyclic = [], [], 0, 0, []
        with self._tx():
            for p in propositions:
                p = p or {}
                name, statement = str(p.get("name", "")).strip(), str(p.get("statement", "")).strip()
                if len(name) < 3 or len(statement) < 10:
                    raise LearnError(f"Each proposition needs a short name and a full-sentence statement; got {p!r}.")
                key = key_of(name)
                if self._prop_id(key):
                    reused.append(name)
                    continue
                self.conn.execute("INSERT INTO propositions(id, key, name, statement, lesson_id, source, created_at) "
                                  "VALUES (?,?,?,?,?,?,?)", (_new_id("p"), key, name, statement, lesson_id, source, _now()))
                added.append(name)
            for c in chains:
                c = c or {}
                conclusion = self._resolve(c.get("conclusion", ""))
                premises = {self._resolve(x) for x in (c.get("premises") or [])}
                if not premises:
                    raise LearnError("Each chain needs at least one premise.")
                if conclusion in premises or self._reaches(conclusion, premises):
                    if skip_cycles:
                        cyclic.append(c.get("conclusion"))
                        continue
                    if conclusion in premises:
                        raise LearnError(f"'{c.get('conclusion')}' cannot be its own premise.")
                    raise LearnError(f"Rejected as circular: '{c.get('conclusion')}' already supports one of its "
                                     "own premises. Nothing from this call was saved.")
                if self._chain_exists(conclusion, premises):
                    dup += 1
                    continue
                chain_id = _new_id("c")
                self.conn.execute("INSERT INTO chains(id, conclusion, lesson_id, created_at) VALUES (?,?,?,?)",
                                  (chain_id, conclusion, lesson_id, _now()))
                self.conn.executemany("INSERT INTO chain_premises(chain_id, premise) VALUES (?,?)",
                                      [(chain_id, pid) for pid in sorted(premises)])
                added_chains += 1
        return {"added_propositions": added, "reused_propositions": reused, "added_chains": added_chains,
                "duplicate_chains": dup, "skipped_circular": cyclic}

    def premises_of(self, proposition_id: str) -> list[str]:
        return [r[0] for r in self._all(
            "SELECT DISTINCT pr.name FROM chains c JOIN chain_premises cp ON cp.chain_id=c.id "
            "JOIN propositions pr ON pr.id=cp.premise WHERE c.conclusion=? ORDER BY pr.name", (proposition_id,))]

    def search(self, query: str, limit: int = 6) -> list[dict]:
        wanted = _tokens(query or "")
        if not wanted:
            return []
        scored = []
        for row in self._all("SELECT * FROM propositions"):
            score = len(wanted & _tokens(row["name"] + " " + row["statement"]))
            if score:
                scored.append((score, row))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["created_at"]))
        return [{**dict(row), "score": score, "premises": self.premises_of(row["id"])}
                for score, row in scored[: max(1, int(limit))]]

    def lesson_props(self, lesson_id: str, limit: int = 8) -> list[dict]:
        return [dict(r) for r in self._all(
            "SELECT * FROM propositions WHERE lesson_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (lesson_id, limit))]

    def recent_props(self, limit: int = 15) -> list[dict]:
        return [dict(r) for r in self._all(
            "SELECT * FROM propositions ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))]

    def graph(self) -> dict:
        """Whole graph for the Desktop graph view."""
        props = [{"id": r["id"], "name": r["name"], "statement": r["statement"], "source": r["source"]}
                 for r in self._all("SELECT * FROM propositions ORDER BY created_at, rowid")]
        chains = []
        for r in self._all("SELECT id, conclusion FROM chains ORDER BY created_at, rowid"):
            chains.append({"id": r["id"], "conclusion": r["conclusion"], "premises": [
                p[0] for p in self._all("SELECT premise FROM chain_premises WHERE chain_id=?", (r["id"],))]})
        return {"propositions": props, "chains": chains}

    def stats(self) -> dict:
        def count(table):
            return self._one(f"SELECT COUNT(*) FROM {table}")[0]  # noqa: S608 fixed table names
        return {"lessons": count("lessons"), "propositions": count("propositions"), "chains": count("chains")}


def _parse_assessment_text(text: str) -> dict:
    """'strand: assessment' per line (bullets allowed); a 'Summary:' line becomes the summary."""
    strands, summary = [], ""
    for line in text.splitlines():
        line = line.strip().lstrip("-*• ").strip()
        name, sep, body = line.partition(":")
        if not sep:
            continue
        if name.strip().lower() == "summary":
            summary = body.strip()
        else:
            strands.append({"strand": name.strip(), "assessment": body.strip()})
    out = {"strands": strands}
    if summary:
        out["summary"] = summary
    return out


def _validate_assessment(assessment) -> dict:
    if isinstance(assessment, str):
        assessment = _parse_assessment_text(assessment)
    strands = (assessment or {}).get("strands") if isinstance(assessment, dict) else None
    if not strands or not isinstance(strands, list):
        raise LearnError("Moving to plan requires `assessment`: plain text, one 'strand: assessment' line per "
                         "dependency the lesson rests on (floor, ceiling, misconceptions, what to build from), "
                         "plus a 'Summary: ...' line.")
    out = []
    for s in strands:
        s = s or {}
        name, text = str(s.get("strand", "")).strip(), str(s.get("assessment", "")).strip()
        if not name or len(text) < 10:
            raise LearnError(f"Each strand needs `strand` and an `assessment` sentence; got {s!r}.")
        out.append({"strand": name, "assessment": text})
    summary = str(assessment.get("summary", "")).strip()
    return {"strands": out, "summary": summary} if summary else {"strands": out}


def _validate_answer(q, choices, text, dont_know, confidence) -> dict:
    dont_know = bool(dont_know)
    if dont_know:
        return {"choices": [], "text": "", "dont_know": True, "confidence": None}
    if q["options"]:
        try:
            choices = sorted({int(c) for c in (choices or [])})
        except (TypeError, ValueError):
            raise LearnError("choices must be option indices.") from None
        if not choices or any(not 0 <= c < len(q["options"]) for c in choices):
            raise LearnError("Pick at least one valid option, or answer 'I don't know'.")
        text = ""
    else:
        choices, text = [], (text or "").strip()
        if not text:
            raise LearnError("Write an answer, or answer 'I don't know'.")
    if confidence is not None:
        try:
            confidence = int(confidence)
        except (TypeError, ValueError):
            raise LearnError("confidence must be a percentage 0-100.") from None
        if not 0 <= confidence <= 100:
            raise LearnError("confidence must be a percentage 0-100.")
    return {"choices": choices, "text": text[:8000], "dont_know": False, "confidence": confidence}
