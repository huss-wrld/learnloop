"""Score a driven learnloop lesson: protocol, reliability, method, guard, cost.

    python3 tools/scorecard.py <run-name>

Reads the learnloop-test profile's state.db (transcript, tool calls), the run log written by drive.py,
and the skills/memory files. Prints a markdown scorecard with message ids for every flag, saves it to
runs/<run>/scorecard.md and appends the numbers to runs/history.jsonl. Teaching quality is not scored:
read the flagged messages and the transcript for that.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from statistics import median

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from drive import PROFILE_HOME, RUNS, snapshot  # noqa: E402

QUESTION = re.compile(r"\*\*Question\.\*\*")
CARD = re.compile(r"^::learnloop-question\{id=\"(q_[0-9a-f]+)\"\}\s*$", re.M)
LEARN = ("learn_ask", "learn_grade", "learn_phase", "learn_method", "learn_record", "learn_recall")


def load(run: str):
    d = RUNS / run
    state = json.loads((d / "state.json").read_text())
    turns_log = [json.loads(line) for line in (d / "turns.jsonl").read_text().splitlines() if line.strip()]
    db = sqlite3.connect(f"file:{PROFILE_HOME / 'state.db'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    msgs = [dict(r) for r in db.execute(
        "SELECT id, role, content, tool_name, tool_calls, timestamp FROM messages WHERE session_id=? ORDER BY id",
        (state["session_id"],))]
    return d, state, turns_log, msgs


def split_turns(msgs):
    turns, cur = [], None
    for m in msgs:
        if m["role"] == "user":
            cur = {"user": m, "items": []}
            turns.append(cur)
        elif cur is not None:
            cur["items"].append(m)
    return turns


def tool_json(m):
    try:
        return json.loads(m["content"] or "")
    except (json.JSONDecodeError, TypeError):
        return {}


def strip_questions(text: str) -> str:
    """Visible text without the question blocks (everything from **Question.** to the end of that block)."""
    return CARD.sub("", QUESTION.split(text)[0]).strip() if text else ""


def score(run: str) -> str:
    d, state, turns_log, msgs = load(run)
    turns = split_turns(msgs)
    ldb = sqlite3.connect(f"file:{PROFILE_HOME / 'plugin-data/learnloop/learnloop.db'}?mode=ro", uri=True)
    # question types in grading order: the n-th learn_grade graded the n-th answered question
    graded_types = [r[0] for r in ldb.execute(
        "SELECT q.qtype FROM questions q JOIN lessons l ON l.id = q.lesson_id WHERE l.session_id = ? "
        "AND q.status = 'answered' ORDER BY q.answered_at, q.rowid", (state["session_id"],))]
    phase, open_q = "probe", False
    flags = {k: [] for k in ("hand_typed", "doubled", "not_graded_first", "probe_teaching",
                             "early_record", "errors", "parse_errors", "blocked", "explained_after_miss")}
    counts = {"questions_asked": 0, "graded": 0, "records": 0, "refusals": 0, "turns": len(turns),
              "teach_misses": 0, "check_misses": 0}
    phases_seen = ["probe"]
    for i, t in enumerate(turns):
        tools = [m for m in t["items"] if m["role"] == "tool"]
        texts = [m for m in t["items"] if m["role"] == "assistant" and (m["content"] or "").strip()]
        learn_calls = [m for m in tools if m["tool_name"] in LEARN]
        asks_ok = [m for m in tools if m["tool_name"] == "learn_ask" and "error" not in tool_json(m)]
        counts["questions_asked"] += len(asks_ok)
        # questions shown vs asked through learn_ask
        blocks = [b.strip() for m in texts for b in QUESTION.split(m["content"])[1:]]
        blocks += [c for m in texts for c in CARD.findall(m["content"])]
        shown = len(set(blocks))
        if len(blocks) > shown:
            flags["doubled"].append(texts[-1]["id"])
        if shown > len(asks_ok):
            flags["hand_typed"].append(f"{texts[-1]['id']} ({shown} shown, {len(asks_ok)} via learn_ask)")
        # grade first
        if i > 0 and open_q:
            first = learn_calls[0]["tool_name"] if learn_calls else None
            if first != "learn_grade":
                flags["not_graded_first"].append(f"{t['user']['id']} (first learnloop call: {first})")
        last_grade = None
        missed_in_teach = False
        for m in tools:
            res = tool_json(m)
            content = m["content"] or ""
            if "Blocked by learnloop" in content:
                flags["blocked"].append(f"{m['id']} {m['tool_name']}")
            if "error" in res or content.startswith('{"error"'):
                err = str(res.get("error", content))[:120]
                if "learn_grade first" in err:
                    counts["refusals"] += 1
                elif "not valid JSON" in err or "requires a 'name'" in err:
                    flags["parse_errors"].append(f"{m['id']} {err}")
                elif "Blocked by learnloop" not in err:
                    flags["errors"].append(f"{m['id']} {m['tool_name']}: {err}")
                continue
            if m["tool_name"] == "learn_grade":
                counts["graded"] += 1
                last_grade = res
                open_q = False
                qtype = graded_types[counts["graded"] - 1] if counts["graded"] <= len(graded_types) else None
                if phase == "teach" and res.get("verdict") in ("wrong", "partial", "dont_know"):
                    counts["teach_misses"] += 1
                    if qtype == "check":  # a missed prediction is SUPPOSED to be followed by teaching
                        missed_in_teach = True
                        counts["check_misses"] += 1
            elif m["tool_name"] == "learn_ask":
                open_q = True
            elif m["tool_name"] == "learn_record":
                counts["records"] += 1
                if not last_grade or last_grade.get("verdict") != "correct" or (last_grade.get("confidence") or 0) < 70:
                    flags["early_record"].append(f"{m['id']} (last grade this turn: "
                                                 f"{(last_grade or {}).get('verdict')}/{(last_grade or {}).get('confidence')})")
            elif m["tool_name"] == "learn_phase" and res.get("phase"):
                if res["phase"] != phase:
                    phase = res["phase"]
                    phases_seen.append(phase)
        # teaching during the probe: long prose outside question blocks while still probing
        if phase == "probe" or (phases_seen[-1] == "plan" and "plan" not in [tool_json(m).get("phase") for m in tools]):
            prose = "\n".join(strip_questions(m["content"]) for m in texts)
            if phase == "probe" and (len(prose) > 600 or "## " in prose):
                flags["probe_teaching"].append(f"{texts[-1]['id'] if texts else t['user']['id']} ({len(prose)} chars prose)")
        if missed_in_teach:
            prose = "\n".join(strip_questions(m["content"]) for m in texts)
            if len(prose) > 600:
                flags["explained_after_miss"].append(f"{texts[-1]['id'] if texts else t['user']['id']} ({len(prose)} chars)")
    # background writes
    before, after = state.get("baseline_files", {}), snapshot()
    changed = sorted(f for f, mt in after.items() if before.get(f) != mt)
    secs = [t["seconds"] for t in turns_log]
    # stream-json reports session totals: per-turn cost is the difference
    cum = [((t.get("tokens") or {}).get("input") or 0) for t in turns_log]
    tok_in = [b - a for a, b in zip([0] + cum[:-1], cum)]
    cum_cached = [((t.get("tokens") or {}).get("cache_read") or 0) for t in turns_log]
    rows = [
        ("Questions asked via learn_ask", counts["questions_asked"], ""),
        ("Questions typed without learn_ask", len(flags["hand_typed"]), "; ".join(flags["hand_typed"])),
        ("Questions shown twice", len(flags["doubled"]), ", ".join(map(str, flags["doubled"]))),
        ("Answers graded", counts["graded"], ""),
        ("Turns not starting with learn_grade (question open)", len(flags["not_graded_first"]),
         "; ".join(flags["not_graded_first"])),
        ("Grade-first refusals", counts["refusals"], ""),
        ("Facts saved / saved without a correct >=70% grade", f"{counts['records']} / {len(flags['early_record'])}",
         "; ".join(flags["early_record"])),
        ("Parse failures", len(flags["parse_errors"]), "; ".join(flags["parse_errors"])),
        ("Other tool errors", len(flags["errors"]), "; ".join(flags["errors"])),
        ("Probe turns with teaching (check)", len(flags["probe_teaching"]), "; ".join(flags["probe_teaching"])),
        ("Teach misses (all / checks) · check misses answered with a long explanation (>600 chars)",
         f"{counts['teach_misses']} / {counts['check_misses']} · {len(flags['explained_after_miss'])}",
         "; ".join(flags["explained_after_miss"])),
        ("Blocked by lesson guard", len(flags["blocked"]), "; ".join(flags["blocked"])),
        ("Skills/memory files changed", len(changed), ", ".join(changed)),
        ("Phases reached", " → ".join(phases_seen), ""),
        ("Turns / median s / max s", f"{len(turns)} / {median(secs) if secs else 0} / {max(secs) if secs else 0}", ""),
        ("Input tokens per turn: median / max", f"{int(median(tok_in)) if tok_in else 0} / {max(tok_in) if tok_in else 0}", ""),
        ("Input tokens whole lesson (cached)", f"{cum[-1] if cum else 0} ({cum_cached[-1] if cum_cached else 0})", ""),
    ]
    model = state.get("model") or {"model": "profile default"}
    out = [f"# Scorecard: {run}", "", f"Session `{state['session_id']}` · topic: {state['topic']} · "
           f"model: {' / '.join(model.values())}", "",
           "| Check | Result | Where (message ids) |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    text = "\n".join(out) + "\n"
    (d / "scorecard.md").write_text(text, encoding="utf-8")
    with open(RUNS / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"run": run, "at": time.time(), **{a: b for a, b, _ in rows}}) + "\n")
    return text


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(score(sys.argv[1]))
