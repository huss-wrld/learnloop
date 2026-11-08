# Known issues and pitfalls

Platform limits and model behaviours that learnloop works around rather than solves.
Each entry has: what happens, the evidence, what we do now, permanent options, and the signal that should make us revisit it.
Hermes source references are to `v0.23.0` (`~/Projects/learnloop-ref/hermes-v0.23.0`).

Status legend: **Mitigated** (workaround in place), **Planned** (workaround agreed, not built yet), **Open** (known, not handled), **Accepted** (by design).

State as of 8 Nov 2026. Update the status when a planned fix lands.

---

## KI-1. Tool arguments break or corrupt in Hermes's tool-search bridge (Planned)

**What happens.** Tool search is on by default for every Hermes user (`tools.tool_search.enabled: auto`, an alias of `on`). Plugin tools are always eligible for deferral, and a plugin can't opt out (`tools/tool_search.py:150`). The model then reaches learnloop's tools through the `tool_call` bridge, whose `calls` argument is an array of `{name, arguments}`. Some models send `calls` as a **JSON string containing JSON** instead of a real array. Hermes tolerates that and parses the string (`tools/tool_search_validation.py:156-160`), but LaTeX now passes through two levels of escaping, and two things can go wrong:

1. **Hard failure.** An invalid escape like `\m` (from `\mathbb`) or `\c` (from `\cdot`) makes `json.loads` fail: `tool_call 'calls' is not valid JSON: Expecting ',' delimiter`. The call never reaches learnloop.
2. **Silent corruption.** Valid JSON escapes that LaTeX happens to contain decode without error into control characters: `\f` (form feed: `\frac` → `<FF>rac`), `\n` (`\nabla` → newline + `abla`, `\neq`, `\nu`), `\t` (`\theta`, `\times`, `\text`, `\tau`), `\b` (`\beta`, `\bar`), `\r` (`\rho`, `\right`). The call succeeds with damaged text.

Dollar signs are **not** the problem: `$` has no special meaning in JSON. Escaping them changes nothing.

**Evidence (dogfood #1, 8 Nov 2026, deepseek-v4.1-flash).**
- "Bare greeting" chat (`local-5e3ba8ef…`), messages 13082-13087: three consecutive `learn_phase` calls (1.5k-2.1k chars, nested assessment JSON + Mermaid plan + LaTeX) failed to parse. The third triggered Hermes's loop warning. That turn took 135 s.
- All 10 `learn_ask` calls in both chats succeeded. A scan of all 11 stored questions found **0** with corrupted escapes (control characters, or a line break followed by `rac`, `abla`, `eq`, `ot`, `ext`, `imes`, `eta`, `ight`, `ambda`, `u`).
- So far: large payloads fail; small ones survive.

**Agreed fix (not built yet; today the assessment is plain text, the plan is still a tool argument).**
- Plan and assessment no longer travel as tool arguments. The model writes them as fenced blocks in its reply; the `transform_llm_output` hook extracts, validates and stores them. `learn_phase` carries only the phase name. (Cost: validation errors reach the model on the next turn, not immediately.)
- Questions must stay tool calls, because the answer key must not be visible in the reply. Hardening:
  - the method and the per-turn reminder say: pass `calls` as an array, never as a string;
  - learnloop rejects question fields containing escape debris (`\x08`, `\x0c`, `\t`, `\r`, or a line break directly followed by a known LaTeX command tail) with "your LaTeX was mangled in transit; resend this question";
  - guideline: keep `explanation` under ~600 chars and teach the long version in prose after grading.

**Permanent options (not done).**
- **Upstream fix in Hermes (best).** In `tool_search_validation.py`, when `calls` arrives as a string, repair it before parsing: double any backslash not followed by a valid escape, and treat `\f`, `\b` (and `\n`, `\t`, `\r` when followed by letters) as LaTeX. Fixes it for every plugin. Out of scope for the hackathon; a good post-hackathon PR.
- **Ask Hermes for a per-plugin "never defer" flag** (e.g. a manifest field), so learnloop's six small tools stay directly callable. Its tool listing is ~2k tokens, cheap enough to keep eager.
- **User-side:** `tools.tool_search.enabled: off`. Global and the user's choice, so only a documented tip.
- **Encode LaTeX-heavy fields ourselves**, e.g. ask the model to write `\\` explicitly, or base64. Rejected: it moves the burden onto the model, which is the failing party.
- **Hold-stream transform for questions:** put the whole question (key included) in the reply and strip the key with a `hold_stream=True` transform before the user sees it. Rejected for now: the hook is global, so it would delay streaming in *every* chat, not just lessons.

**Revisit when.** Any of: a parse-failure rate above ~1 in 20 `learn_ask` calls across dogfood sessions; any corrupted question reaching the learner; a model that systematically stringifies `calls`; Hermes adding a per-plugin eager flag or fixing the bridge.

---

## KI-2. Slash-command output is plain text in Desktop (Planned)

**What happens.** Desktop renders a plugin command's reply as a system message with `whitespace-pre-wrap` and no markdown (`apps/desktop/src/components/assistant-ui/thread/system-message.tsx:157-170`). Mermaid blocks, tables and bold show as raw text.

**Evidence.** `/study map` printed the raw ```` ```mermaid ```` source (user screenshot, 8 Nov).

**Agreed fix (side pane not built yet).** Command replies are short plain sentences. Visual content (plan, position, open question) lives in the Desktop **Lesson side pane**, refreshed from learnloop's backend. `/study map` points to the pane.

**Permanent options.** Ask Hermes to render command output as markdown (a flag on the command result). Not needed while the pane exists.

**Revisit when.** We need rich output on a platform without the pane (CLI, Telegram).

---

## KI-3. Plugin commands can't start a model turn (Mitigated)

**What happens.** A plugin slash command returns text only (`hermes_cli/plugin_command_dispatch.py`). `/study <topic>` could create the lesson but the user had to send another message ("go") before anything happened. That also gave chats junk titles ("Go", "Bare greeting"), since Hermes titles from the first message.

**What we do now.** The lesson entry point is a **plugin-bundled skill**, `/learnloop:study <topic>` (`skills/study/SKILL.md`, generated from `method/` by `tools/build_skill.py`; a test fails if it's stale). Hermes turns plugin skills into slash commands that put the skill text into the user's message and start a turn immediately (`agent/skill_commands.py:689-735, 843-853`). The `pre_llm_call` hook looks for Hermes's fixed marker (`invoked the "learnloop:study" skill, indicating`) and, after it, the topic line (`The user has provided the following instruction alongside the skill invocation: …`), then starts the lesson in code. The model can't start a lesson by itself: loading the skill via `skill_view` gives a tool result, not a user message with the marker, and a user merely naming the skill doesn't match the marker either.

**Spike (8 Nov, Desktop):** the turn started at once; the hook got the marker with `platform=desktop`; the topic came through; the chat was titled "Study how perceptrons learn". Verified again against Hermes's own `build_skill_invocation_message` for `/learnloop:study`.

**Edge cases handled.** No topic (`/learnloop:study` alone): no lesson; the model asks for a topic. Invoked while a lesson is active: no restart; the model says to `/study stop` first or use a new chat. Hermes's `extract_user_instruction_from_skill_message` returns the *whole* message when no skill was invoked, so learnloop never uses it without the marker.

**Limits.**
- **Messaging platforms.** Hermes offers plugin skills as commands only on interactive surfaces (Desktop, TUI, CLI chat; `split_stacked_skill_commands`: "plugin skills are interactive-only"). On Telegram etc. `/study <topic>` still starts the lesson and the user sends a first message to begin. On interactive surfaces `/study <topic>` points to `/learnloop:study`.
- **Single-query CLI** (`hermes chat -q "/learnloop:study …"`) answers "Unknown command": it isn't interactive.
- **The skill is listed in every session's skills index** (one line). Hermes has no frontmatter flag to hide a skill from the model; the description says "User-invoked only".
- **Coupled to two Hermes strings.** If a Hermes update rewords the marker or the topic line, lessons stop starting (no crash). `tests/test_core.py::skill_message` mirrors the strings; re-run the live check above after Hermes upgrades.

**Rejected options.** Hermes's `inject_tui_message` / `inject_gateway_message` (`hermes_cli/plugins.py:1166-1200`) can start turns but are internal, not plugin API: catalog risk and liable to break on updates. A Desktop-only auto-submit would leave CLI and Telegram needing "go".

**Revisit when.** Hermes exposes a public "start turn" API for plugin commands, offers plugin skills on messaging platforms, or changes the marker format.

---

## KI-4. Plugin command names can silently collide with built-ins (Mitigated)

**What happens.** A plugin command with a built-in's name is skipped with only a log warning (`hermes_cli/plugins.py:660-665`). `hermes plugins validate` does **not** report it. `/learn` is a built-in (learn a skill from anything), so our original `/learn` would never have worked.

**What we do now.** Renamed to `/study`; a test asserts the help text doesn't use `/learn`. Check new names with `hermes_cli.commands.resolve_command(name)` before shipping.

**Revisit when.** Hermes adds a built-in named `study` or `learnloop:*`; re-run the collision check on every Hermes upgrade.

---

## KI-5. Models paste the question twice in text mode (Mitigated)

**What happens.** In text mode `show` is the full formatted question. Models read "present the question and end with `show`" as two actions and output the question twice.

**Evidence.** 4 of 10 questions doubled in dogfood #1 (messages 12975, 13069, 13080, 13099). The model's reasoning in 13069: "I'll present the question and end with show as final paragraph."

**What we do now.** The `learn_ask` result says `show` is the complete question, to be pasted exactly once. Safety net: the `transform_llm_output` hook collapses a repeated `show` to its last copy. The transform runs after streaming, so the learner can still briefly see the double while it streams; the stored chat is clean. Desktop cards avoid the issue (one short directive line).

**Revisit when.** Doubles persist with the new instruction, or another output-shape habit shows up (e.g. paraphrasing the question before `show`).

---

## KI-6. Tools can't tell Desktop from CLI (Mitigated)

**What happens.** Inside a tool, `HERMES_SESSION_PLATFORM` is `local` for both Desktop and CLI. Only the `pre_llm_call` hook receives `platform="desktop"`.

**What we do now.** The hook records the platform per session id in memory; tools read it from there. If a tool somehow runs before any hook call in a process (e.g. after a plugin reload mid-turn), it falls back to text mode.

**Revisit when.** Hermes passes the platform to tool handlers.

---

## KI-7. The Desktop half has its own enable switch (Mitigated)

**What happens.** `hermes plugins enable` enables the Python half only. The Desktop half (cards, side pane) must be switched on separately in Desktop → Capabilities → Plugins, and is off by default. With it off, a card directive shows as raw `::…` text.

**Evidence.** Spike U4 (8 Nov): raw text until the Desktop half was enabled.

**What we do now.** learnloop uses cards only after the Desktop half has pinged the backend at least once (`desktop_ui = seen`); otherwise text mode. README and the first lesson reply must tell users where the switch is.

**Revisit when.** The Desktop half is disabled after having been seen (the setting is sticky), so a user who turns it off later would get raw directives. Fix: the Desktop half re-pings on load, and expire `seen` after ~24 h without a ping.

---

## KI-8. Compression changes the chat's session id (Mitigated)

**What happens.** Context compression continues the chat under a new child session id (`agent/conversation_compression.py:1574-1640`). Lessons are keyed by session id and would be lost.

**What we do now.** Before each hook call and tool call, if the session has no lesson, learnloop walks up `parent_session_id` (max 5 levels, read-only `SessionDB`) while the parent ended with `end_reason == "compression"`, and rebinds the lesson. Branches/forks are not followed, so a branch doesn't steal the original's lesson.

**Not yet verified live.** No dogfood lesson has hit compression yet.

**Revisit when.** A lesson disappears after a long session; or Hermes exposes a plugin hook with the old and new session ids.

---

## KI-9. Lessons of deleted chats stayed open (Mitigated)

**What happens.** A lesson whose chat was deleted could never be stopped (`/study stop` needs the chat).

**Evidence.** Lesson `l_129a0ab59aac` (session `local-3cdb93…`, no longer in `state.db`) is still open in the test database.

**What we do now.** The `on_session_delete` hook ends the lesson. Lessons orphaned before this hook existed stay open; they're harmless (no chat can reach them) and can be swept by a one-off clean-up.

---

## KI-10. Hermes auto-creates skills from lesson chats (Planned)

**What happens.** Hermes's background skill learning wrote `~/.hermes/skills/learnloop-lesson/SKILL.md` from the perceptron lesson. It then appears in the skills index and can be loaded into lesson chats next to learnloop's method, giving the model two competing instruction sets. Its content drifts from ours (it described the nested-JSON assessment after we removed it).

**Agreed fix.** Delete the auto-created copy (not done yet). The baseline is LearnHarness's prompts, shipped as learnloop plugin skills; auto-created skills are not a source.

**Permanent options.** README note telling users to delete such skills; or a learnloop check (in `/study status`) that warns when a non-plugin skill named `learnloop*` exists. Check whether Hermes's skill learning can be told to skip sessions (e.g. a session flag a plugin can set).

**Revisit when.** Users report lessons drifting from the method, or auto-created learnloop skills reappear.

---

## KI-11. Model compliance with the method (Open, inherent)

**What happens.** Everything that is not enforced in code depends on the model following the method: one question per turn, teaching before checks, recording after a step lands. learnloop enforces what it can (phase order, one open question, answer keys, acyclic graph, plan required before teaching) but can't force good teaching.

**Evidence.** deepseek-v4.1-flash followed the method well in dogfood #1 apart from KI-1 and KI-5. Other models are untested.

**Revisit when.** Testing other models (the hackathon judges may use any). Keep a small checklist of behaviours to score per model: probes before teaching, never answers its own question, grades first, records after landings.
