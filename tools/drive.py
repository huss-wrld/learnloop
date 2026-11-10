"""Drive a learnloop lesson headlessly in the learnloop-test profile, one learner turn at a time.

    python3 tools/drive.py start <run-name> <topic...>   # sends /learnloop:study <topic>
    python3 tools/drive.py say <run-name> <message...>    # next learner message
    python3 tools/drive.py show <run-name>                # last visible reply again
    python3 tools/drive.py answer <run-name> [--choices B,C] [--text ...] [--idk] [--confidence 30]
                                  [--thinking ...] [--reading ...]   # answer the open card like a click

Model per run: set DRIVE_MODEL / DRIVE_PROVIDER / DRIVE_REASONING when starting; they're saved with the run.

Prints only what a learner would see (the assistant's reply text), plus tool NAMES for orientation.
Tool results (answer keys, assessments) are never printed: the person playing the learner must not see them.
Everything is logged to ~/Projects/learnloop-ref/runs/<run-name>/.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

PROFILE = "learnloop-test"
HOME = Path.home()
PROFILE_HOME = HOME / ".hermes/profiles" / PROFILE
RUNS = HOME / "Projects/learnloop-ref/runs"
HERMES_WS = Path(os.environ.get(
    "HERMES_WS", HOME / ".hermes/installs/e00cfdc438b1ed6d/environments/376dc4c4a21c40b4ab37e3ad15091b93/workspace"))
TIMEOUT = 600


def skill_message(topic: str) -> str:
    """The exact user message Hermes builds for `/learnloop:study <topic>` (built by Hermes itself)."""
    code = ("import sys; sys.path.insert(0, '.'); "
            "from agent.skill_commands import build_skill_invocation_message as b; "
            f"sys.stdout.write(b('/learnloop:study', {topic!r}))")
    out = subprocess.run([str(HERMES_WS.parent / "venv/bin/python"), "-I", "-W", "ignore", "-c", code],
                         cwd=HERMES_WS, env={**os.environ, "HERMES_HOME": str(PROFILE_HOME)},
                         capture_output=True, text=True, check=True)
    if "learnloop:study" not in out.stdout:
        sys.exit("could not build the skill message: is learnloop enabled in the test profile?")
    return out.stdout


def snapshot() -> dict:
    """Skills and memory files, to detect background-review writes during the run."""
    files = {}
    for sub in ("skills", "memories"):
        for p in (PROFILE_HOME / sub).rglob("*"):
            if p.is_file() and ".curator" not in str(p) and p.name != ".usage.json":
                files[str(p.relative_to(PROFILE_HOME))] = p.stat().st_mtime
    return files


def plugin_py(code: str) -> str:
    """Run Python against the test profile's learnloop (same store the card's backend route uses)."""
    pre = "import sys, json; sys.path.insert(0, %r); import learnloop; from learnloop import core; " \
          "store = learnloop.get_store(); " % str(HOME / "Projects")
    out = subprocess.run([str(HERMES_WS.parent / "venv/bin/python"), "-I", "-W", "ignore", "-c", pre + code],
                         cwd=HERMES_WS, env={**os.environ, "HERMES_HOME": str(PROFILE_HOME)},
                         capture_output=True, text=True)
    if out.returncode:
        sys.exit(out.stderr[-1500:])
    return out.stdout


def render_cards(reply: str) -> str:
    """Show each ::learnloop-question card as the learner sees it: prompt and options, never the key."""
    import re
    def card(m):
        q = json.loads(plugin_py(f"print(json.dumps(store.public_question({m.group(1)!r})))"))
        lines = [f"[CARD {q['id']} · {q.get('qtype') or 'probe'}{' · select all that apply' if q['multi'] else ''}]",
                 q["prompt"]]
        lines += [f"{'ABCDEFGH'[i]}) {o}" for i, o in enumerate(q["options"])] or ["(free answer)"]
        return "\n".join(lines)
    return re.sub(r'^::learnloop-question\{id="(q_[0-9a-f]+)"\}\s*$', card, reply, flags=re.M)


def visible_reply(session_id: str, after_ts: float) -> str:
    db = sqlite3.connect(f"file:{PROFILE_HOME / 'state.db'}?mode=ro", uri=True)
    rows = db.execute("SELECT content FROM messages WHERE session_id=? AND role='assistant' AND timestamp>=? "
                      "ORDER BY id", (session_id, after_ts)).fetchall()
    return "\n\n".join(r[0] for r in rows if (r[0] or "").strip())


def turn(run: str, message: str, first: bool) -> None:
    d = RUNS / run
    d.mkdir(parents=True, exist_ok=True)
    state_file = d / "state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    if first:
        if state:
            sys.exit(f"run {run} exists; pick a new name")
        state = {"run": run, "topic": message, "started": time.time(), "baseline_files": snapshot(), "turns": 0,
                 "model": {k: os.environ[f"DRIVE_{k.upper()}"] for k in ("model", "provider", "reasoning")
                           if os.environ.get(f"DRIVE_{k.upper()}")}}
        message = skill_message(message)
    elif "session_id" not in state:
        sys.exit(f"run {run} has no session yet; use start")
    (d / "msg.txt").write_text(message, encoding="utf-8")
    cmd = ["hermes", "-p", PROFILE, "chat", "-Q", "--source", "cli", "--format", "stream-json",
           "--query-file", str(d / "msg.txt")]
    if not first:
        cmd += ["--resume", state["session_id"]]
    for key, flag in (("model", "-m"), ("provider", "--provider"), ("reasoning", "--reasoning")):
        if state.get("model", {}).get(key):
            cmd += [flag, state["model"][key]]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        proc, timed_out = exc, True
    events = []
    for line in (proc.stdout or "").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    result = next((e for e in events if e.get("type") == "result"), {})
    sid = result.get("session_id") or state.get("session_id")
    if not sid:
        sys.exit(f"no session id; stderr:\n{(proc.stderr or '')[-800:]}")
    state["session_id"] = sid
    state["turns"] += 1
    tools = [e.get("name") for e in events if e.get("type") == "tool_use"]
    rec = {"turn": state["turns"], "sent_at": t0, "seconds": round(time.time() - t0, 1), "timed_out": timed_out,
           "learner": message if not first else f"/learnloop:study {state['topic']}", "tools": tools,
           "tokens": result.get("tokens"), "exit_code": result.get("exit_code")}
    with open(d / "turns.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    state_file.write_text(json.dumps(state, indent=1))
    reply = render_cards(visible_reply(sid, t0 - 1))
    (d / "last_reply.md").write_text(reply, encoding="utf-8")
    print(f"--- turn {rec['turn']} · {rec['seconds']} s · tools: {', '.join(tools) or 'none'}"
          f"{' · TIMED OUT' if timed_out else ''}\n")
    print(reply or "(no visible reply)")


def answer(run: str, argv: list[str]) -> None:
    """Submit to the open card as the Desktop card does, print the reveal, then send the card's chat line."""
    import argparse
    ap = argparse.ArgumentParser(prog="drive.py answer")
    for a in ("--choices", "--text", "--confidence", "--thinking", "--reading"):
        ap.add_argument(a, default="")
    ap.add_argument("--idk", action="store_true")
    a = ap.parse_args(argv)
    sid = json.loads((RUNS / run / "state.json").read_text())["session_id"]
    choices = ["ABCDEFGH".index(c.strip().upper()) for c in a.choices.split(",") if c.strip()]
    payload = dict(choices=choices or None, text=a.text, dont_know=a.idk,
                   confidence=int(a.confidence) if a.confidence else None, thinking=a.thinking,
                   reading_thinking=a.reading)
    res = json.loads(plugin_py(
        f"les = store.require_lesson({sid!r}); q = store.open_question(les['id']); "
        f"assert q, 'no open question'; q = store.submit(q['id'], **{payload!r}); "
        f"print(json.dumps({{'line': core.card_answer_line(q), 'pub': store.public_question(q['id'])}}))"))
    r = res["pub"].get("result")
    if r:  # what the card shows: verdict and the correct option(s); the explanation stays tucked
        print(f"[card result: {r['verdict']} · correct: {', '.join('ABCDEFGH'[i] for i in r.get('correct', []))}]")
    else:
        print("[card: submitted, waiting for grading]")
    turn(run, res["line"], first=False)


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, run, rest = sys.argv[1], sys.argv[2], " ".join(sys.argv[3:]).strip()
    if cmd == "start" and rest:
        turn(run, rest, first=True)
    elif cmd == "say" and rest:
        turn(run, rest, first=False)
    elif cmd == "answer":
        answer(run, sys.argv[3:])
    elif cmd == "show":
        print((RUNS / run / "last_reply.md").read_text(encoding="utf-8"))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
