# learnloop

Structured lessons inside Hermes. learnloop finds out what you already know, plans a path from there, and teaches it one graded check at a time. What you learn lands in a knowledge graph you can see, practise from, and (if you opt in) let other chats build on.

The teaching method is [LearnHarness](https://github.com/amosblomqvist/learnharness)'s, ported into Hermes as a plugin. Credit for the method belongs there; see [Credit](#credit-and-licence).

## What it does

**Lessons** (`/learnloop:study <topic>`) run in three phases, all inside one chat:

1. **Probe.** Graded questions that measure where your understanding of each strand of the topic starts and stops. The probe measures; it doesn't teach.
2. **Plan.** A map of the steps from what you hold to the goal, drawn as a diagram. You approve it or ask for changes.
3. **Teach.** Step by step: a prediction, then the step, then a check. A missed check gets a smaller question one rung below the miss, building back up until you answer the original yourself. No walls of explanation.

Every question records your answer, your confidence and your thinking. What you learn is saved as facts linked by the reasoning that connects them.

**Practice** (`/learnloop:practice <topic>`) exercises what's already in your graph. One problem at a time, posed with a committed model solution; hints come one rung at a time (from "re-read the second given" up to a worked step), and the solution is revealed only when the problem is concluded. Between problems the session pauses so you can ask about the last one; the next comes when you ask for it.

**The knowledge graph** is every fact you've learned, linked premise to conclusion. In Hermes Desktop it's a live, draggable graph on the Learn page, with adjustable physics, search, and "Practise this" on any fact.

**Recall** (off by default) lets other chats use up to 6 relevant facts from your graph, and says so when it does.

## Install

```bash
hermes plugins install learnloop          # once it's listed in the catalog
hermes plugins install huss-wrld/learnloop      # straight from GitHub
```

Then, in Hermes Desktop, enable learnloop's Desktop part: **Capabilities → Plugins → learnloop → enable**, then **Rescan**. Each profile has its own switch. Without the Desktop part learnloop still works, with questions and problems as text.

Requires Hermes 0.23.0 or later. No API keys, no Python dependencies.

## Use

| Command | What it does |
|---|---|
| `/learnloop:study <topic>` | Start a lesson in this chat |
| `/learnloop:practice <topic>` | Start a practice session in this chat |
| `/learnloop stop` | End the current lesson or practice session |
| `/learnloop status` | This chat's lesson and your graph's size |
| `/learnloop map` | The lesson plan with your position |
| `/learnloop graph [words]` | Search what you've learned |
| `/learnloop recall on\|off` | Let other chats use your graph (off by default) |
| `/learnloop cards on\|off` | Answer cards in Desktop (on by default) |
| `/learnloop import <dir>` | Import a LearnHarness knowledge graph, e.g. `~/.config/LearnHarness/data` |

On Telegram and other messaging platforms, plugin skills aren't available, so start with `/learnloop <topic>` or `/learnloop practice <topic>` instead.

learnloop is inert until you start something: no lesson, no effect on the chat (unless you turned recall on).

## In Hermes Desktop

- **Question dock.** As in LearnHarness, the open question sits on the message box: pick an option (or *I don't know*) and a confidence above it, type your thinking in the box, press Enter. The chat keeps a card for each question; after you answer it shows the verdict and the correct option, with the explanation behind a *Why* toggle. While a question is open, what you type is your answer (slash commands still work).
- **Lesson pane** on the right of the chat: phase, progress, the live plan map, the open question, the facts learned so far. In a practice chat: the problems and their outcomes.
- **Learn page** in the sidebar: start a lesson or practice session, reopen past ones, and explore your knowledge graph.
- **Practice dock.** While a problem is open it sits above the message box; what you type is your thinking. Hint and Set aside are one click; so is Next problem.

## Models

The method asks a lot of the model: restraint during the probe, small questions instead of explanations, tool calls instead of typed questions. Tested so far:

- **Claude Opus 5.5** (medium reasoning): followed the method closely. A 15-turn lesson had no hand-typed questions, no tool errors, and stepped down to smaller questions after misses.
- **DeepSeek V4.1 Flash**: practice sessions ran cleanly. In lessons it sometimes typed a question by hand instead of using the tool (learnloop detects this and corrects course on the next turn).

**Model roles.** LearnHarness runs three model slots: a strong model teaches, a cheap one runs research and other background jobs, a vision one reads images and PDFs. In Hermes those are settings you already have, and learnloop doesn't change your config:

| Role | Hermes setting |
|---|---|
| Teaching (probe, plan, teach, practice) | the chat's model |
| Background research (`delegate_task`) | `delegation.model` / `delegation.provider` (defaults to the chat's model) |
| Images and figures | `auxiliary.vision` |

The teacher verifies facts it isn't sure of by dispatching research in the background and keeps teaching; the brief comes back into the chat with its sources.

Stronger models make better teachers. In these tests a lesson turn sent about 110k to 125k input tokens and a practice turn about 32k, most of it cached.

## What learnloop touches

So you know before installing:

- **Storage.** One SQLite database in Hermes's plugin storage (`<hermes home>/plugin-data/learnloop/learnloop.db`), per profile. Graph layout and physics settings are kept in Desktop's local storage.
- **Network.** None. learnloop makes no network calls of its own.
- **Shell.** None. learnloop runs no commands.
- **Reads outside its own data.** The folder you pass to `/learnloop import` (read-only), and Hermes's session database (read-only) to follow a lesson across context compression, which gives the chat a new session id.
- **Hooks.**
  - `pre_llm_call` adds learnloop's per-turn notes (phase, open question, method reminders) during lessons and practice; with recall on, up to 6 matching facts in other chats.
  - `pre_tool_call` blocks `skill_manage`, `memory`, and loading other skills *during an active lesson only*, so Hermes's background review can't turn a lesson into a competing teaching skill. It fails open.
  - `transform_llm_output` removes a question the model printed twice.
  - `on_session_delete` ends a lesson whose chat was deleted.
- **Background research.** During lessons the method tells the model to verify uncertain facts with Hermes's own `delegate_task` (a background sub-agent that uses your configured web tools). learnloop makes no calls itself; its hook marks the returning brief so it's never graded as your answer.
- **Tools.** `learn_ask`, `learn_grade`, `learn_phase`, `learn_method`, `learn_record`, `learn_recall`, `learn_problem`, `learn_conclude`. All but `learn_recall` refuse to act outside a lesson or practice session.

## Known limits

The full list, with causes and what would change them, is in [docs/known-issues.md](docs/known-issues.md). The ones you'd notice:

- learnloop enforces what it can in code (grade before moving on, one open question, the plan before teaching, the pause in practice), but teaching quality depends on the model.
- A model with shell access can go around learnloop's tools if one refuses it. learnloop's guards cover its own tools only.
- Hermes loads plugin tools on demand, so the first call in a session may take a tool-loading step.
- Background research during a lesson is covered by unit tests (a research result is never graded as your answer) but hasn't been verified in a live lesson yet.

## Compared with LearnHarness, and future work

The teaching method, question types, question dock, practice doctrine, research jobs, demos and the graph's clustering follow LearnHarness. Not yet ported:

- **Graph extraction.** In LearnHarness a separate pipeline writes the graph: an extractor reads the session and an auditor links each new idea to an existing one or adds it. In learnloop the teacher records facts itself with `learn_record` when a step lands, and duplicates merge only by name. Porting the extractor and auditor as background `delegate_task` jobs is the next step.
- **Questions with no right answer** (LearnHarness's `ask_user_question`, e.g. "does this plan fit?"): learnloop asks these in plain chat.
- **Images and files.** LearnHarness can draw visual explanations, mark up your own images with arrows and labels, and read PDFs with a dedicated reader; learnloop relies on Hermes's file tools and vision.
- **Browsing the graph by lesson** (`list_sessions` / `list_propositions`): learnloop's teacher searches it with `learn_recall` instead.
- **Importing notes files** into the graph (needs the extraction pipeline).

## Development

```bash
uvx --with fastapi --with httpx pytest -q tests     # the test suite
hermes plugins validate .                           # catalog checks
python3 tools/build_skill.py                        # regenerate skills/ after editing method/
```

`tools/` and `tests/` are development aids; Hermes never loads them. `tools/drive.py` runs scripted headless lessons (`hermes chat` sessions) in a throwaway test profile you name with `DRIVE_PROFILE`, under that profile's own approval settings, and `tools/scorecard.py` scores them (questions typed by hand, grading order, teaching during the probe, the practice pause, tokens). The research behind the port is in [docs/research](docs/research).

## Credit and licence

The teaching and practice method in `method/` is adapted from **LearnHarness**, Copyright (C) the LearnHarness authors, at commit `713377f366771e3e4730e6acd1bc290e0ebc6d6e`, under AGPL-3.0. Each adapted file names its sources and the changes in its header; the practice doctrine is verbatim. The verbatim originals are in `docs/research/method-raw/`. See [NOTICE](NOTICE).

All Python and JavaScript in this repository is original to learnloop.

Copyright (C) 2026 Hussein Al-Amodi. Licensed under the [GNU Affero General Public License v3.0 only](LICENSE).
