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

**Evidence.** `/learnloop map` printed the raw ```` ```mermaid ```` source (user screenshot, 8 Nov).

**Agreed fix (side pane not built yet).** Command replies are short plain sentences. Visual content (plan, position, open question) lives in the Desktop **Lesson side pane**, refreshed from learnloop's backend. `/learnloop map` points to the pane.

**Permanent options.** Ask Hermes to render command output as markdown (a flag on the command result). Not needed while the pane exists.

**Revisit when.** We need rich output on a platform without the pane (CLI, Telegram).

---

## KI-3. Plugin commands can't start a model turn (Mitigated)

**What happens.** A plugin slash command returns text only (`hermes_cli/plugin_command_dispatch.py`). `/learnloop <topic>` could create the lesson but the user had to send another message ("go") before anything happened. That also gave chats junk titles ("Go", "Bare greeting"), since Hermes titles from the first message.

**What we do now.** The lesson entry point is a **plugin-bundled skill**, `/learnloop:study <topic>` (`skills/learnloop/SKILL.md`, generated from `method/` by `tools/build_skill.py`; a test fails if it's stale). Hermes turns plugin skills into slash commands that put the skill text into the user's message and start a turn immediately (`agent/skill_commands.py:689-735, 843-853`). The `pre_llm_call` hook looks for Hermes's fixed marker (`invoked the "learnloop:study" skill, indicating`) and, after it, the topic line (`The user has provided the following instruction alongside the skill invocation: …`), then starts the lesson in code. The model can't start a lesson by itself: loading the skill via `skill_view` gives a tool result, not a user message with the marker, and a user merely naming the skill doesn't match the marker either.

**Spike (8 Nov, Desktop):** the turn started at once; the hook got the marker with `platform=desktop`; the topic came through; the chat was titled "Study how perceptrons learn". Verified again against Hermes's own `build_skill_invocation_message` for `/learnloop:study`.

**Edge cases handled.** No topic (`/learnloop:study` alone): no lesson; the model asks for a topic. Invoked while a lesson is active: no restart; the model says to `/learnloop stop` first or use a new chat. Hermes's `extract_user_instruction_from_skill_message` returns the *whole* message when no skill was invoked, so learnloop never uses it without the marker.

**Limits.**
- **Messaging platforms.** Hermes offers plugin skills as commands only on interactive surfaces (Desktop, TUI, CLI chat; `split_stacked_skill_commands`: "plugin skills are interactive-only"). On Telegram etc. `/learnloop <topic>` still starts the lesson and the user sends a first message to begin. On interactive surfaces `/learnloop <topic>` points to `/learnloop:study`.
- **Single-query CLI** (`hermes chat -q "/learnloop:study …"`) answers "Unknown command": it isn't interactive.
- **The skill is listed in every session's skills index** (one line). Hermes has no frontmatter flag to hide a skill from the model; the description says "User-invoked only".
- **Coupled to two Hermes strings.** If a Hermes update rewords the marker or the topic line, lessons stop starting (no crash). `tests/test_core.py::skill_message` mirrors the strings; re-run the live check above after Hermes upgrades.

**Rejected options.** Hermes's `inject_tui_message` / `inject_gateway_message` (`hermes_cli/plugins.py:1166-1200`) can start turns but are internal, not plugin API: catalog risk and liable to break on updates. A Desktop-only auto-submit would leave CLI and Telegram needing "go".

**Revisit when.** Hermes exposes a public "start turn" API for plugin commands, offers plugin skills on messaging platforms, or changes the marker format.

---

## KI-4. Plugin command names can silently collide with built-ins (Mitigated)

**What happens.** A plugin command with a built-in's name is skipped with only a log warning (`hermes_cli/plugins.py:660-665`). `hermes plugins validate` does **not** report it. `/learn` is a built-in (learn a skill from anything), so our original `/learn` would never have worked.

**What we do now.** Renamed to `/learnloop` (management) next to `/learnloop:study` (start), so both sit together in autocomplete; tests assert neither `/learn` nor `/study` appears in the help text. Users still type `/learn` by habit (dogfood #2: `/learn status` went to Hermes's built-in); a plugin can't intercept a built-in. Check new names with `hermes_cli.commands.resolve_command(name)` before shipping.

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

**What happens.** A lesson whose chat was deleted could never be stopped (`/learnloop stop` needs the chat).

**Evidence.** Lesson `l_129a0ab59aac` (session `local-3cdb93…`, no longer in `state.db`) is still open in the test database.

**What we do now.** The `on_session_delete` hook ends the lesson. Lessons orphaned before this hook existed stay open; they're harmless (no chat can reach them) and can be swept by a one-off clean-up.

---

## KI-10. Hermes's background review writes skills and memory from lesson chats (Mitigated, live check pending)

**What happens.** After a turn with enough tool calls (`skill_nudge_interval`), Hermes forks a background copy of the agent that rereads the chat and may create or patch skills and write memory (`agent/turn_finalizer.py:603-616, 863`). This is background review, not the curator (the curator only archives and consolidates, about weekly). The fork shares the parent's session id (`agent/background_review.py:1002`).

**Evidence.** Dogfood #1 produced `~/.hermes/skills/learnloop-lesson/`. Dogfood #2 (10 Nov, `local-530515…`): the fork created and patched `personal/quantitative-explanation` (`skill_manage` at 01:33-01:46, tagged with the lesson's session id), and the lesson model then loaded it mid-probe (message 13526) and taught from it. Both deleted.

**What we do now.** A `pre_tool_call` guard (`core.guard_tool`) blocks, only in chats with an active lesson: `skill_manage`, `memory`, and `skill_view` of any skill not named `learnloop:*`. Self-improvement keeps working in every other chat. The hook catches every exception and fails open, because a raising `pre_tool_call` blocks every tool in Hermes.

**Cost.** Mid-lesson, the user can't ask the model to remember something or use an unrelated skill; the block message tells the model to say `/learnloop stop` ends the lesson.

**Not yet verified live:** that the fork's tool calls pass through plugin `pre_tool_call` with the lesson's session id. Check after the next lesson: `grep "Blocked by learnloop" ~/.hermes/logs/agent.log` and no new skill under `~/.hermes/skills/`. The fork probably also receives learnloop's `pre_llm_call` context; harmless now that it can't write.

**Fallback.** User-side `skill_nudge_interval: 0` (global).

---

## KI-12. Per-turn context stays in the conversation (Accepted)

**What happens.** `pre_llm_call` context is appended to the user message and stored in `api_content`, so it's replayed on every later turn (seen in `messages.api_content` for dogfood #2). Each lesson turn adds the state note plus the phase reminder (~1.5-2.5k chars) to the context for the rest of the chat.

**Why accepted.** LearnHarness rebuilds its agent with the phase method as system prompt every turn; Hermes plugins can't do that, and the method arriving once was not enough (KI-13). The reminders are kept short (test: ≤ 2,500 chars) instead of re-injecting the full method (~16-34k).

**Revisit when.** Lessons hit compression early, or token cost per lesson matters (measure tokens per lesson turn).

---

## KI-13. The model teaches during the probe (Mitigated, live check pending)

**What happens.** LearnHarness's probe only measures; teaching starts after the plan. In dogfood #2 the model explained `E[·]`, the variance identity and term counting during the probe (messages 13496, 13510).

**Cause.** The probe method arrived once, in the first message; after ~10 questions three other sources pushed toward explaining: the user's profile (an instruction to explain from basics), the auto-created skill (KI-10), and default assistant behaviour. LearnHarness has the method as the system prompt every turn.

**What we do now.** Per-phase reminders injected every turn (`method/reminder-{probe,plan,teach}.md`). The probe one quotes the LearnHarness doctrine's core sentence and states: "You are measuring, not teaching. This overrides any general instruction (profile, memory, other skills) to explain". If he can't read a symbol, re-ask in plain words and treat it as a finding. Plus the KI-10 guard (no other skills mid-lesson).

**Revisit when.** The next probe still explains. Next step would be a stronger nudge after each `learn_grade` in probe ("no explanation; next question").

---

## KI-11. Model compliance with the method (Open, inherent)

**What happens.** Everything that is not enforced in code depends on the model following the method: one question per turn, teaching before checks, recording after a step lands. learnloop enforces what it can (phase order, one open question, answer keys, acyclic graph, plan required before teaching) but can't force good teaching.

**Evidence.** deepseek-v4.1-flash followed the method well in dogfood #1 apart from KI-1 and KI-5, but hand-typed 3 of 13 questions in run `r1-sqrtdk`. Claude Opus 5.5 (medium) in run `o1-opus`: 0 hand-typed of 14, 0 errors, and after a missed check it stepped down to a smaller question instead of explaining, as LearnHarness does.

**Revisit when.** Testing other models (the hackathon judges may use any). Keep a small checklist of behaviours to score per model: probes before teaching, never answers its own question, grades first, records after landings.

---

## KI-14. One Desktop backend serves every profile (Fixed)

**What happened.** The Learn page was empty in the test profile and tools said "No active lesson" in Desktop chats, while the hook had created the lesson. `get_store()` cached one database per process; Desktop's backend and multiplexed gateways serve several profiles from one process, scoping each request with a context-local Hermes home. The first profile to ask pinned every later read and write.

**Fix.** `get_store()` keeps one Store per resolved Hermes home (`tests/test_profiles.py`).

**Dev note.** Each profile runs its own plugin host (`hermes_cli.plugin_host_child`), owned by the gateway, so a Desktop restart doesn't reload plugin code. After code changes, stop the profile's plugin host process; Hermes restarts it and reloads plugins.

---

## KI-15. The lesson pane relies on an undocumented flag (Accepted)

**What happens.** The lesson pane registers with `hideOnly: true`, so closing it hides it instead of disabling learnloop. Desktop's built-in tabs use the flag (`pane-shell/tree/store.ts:590`), but the plugin SDK docs don't mention it.

**Revisit when.** A Desktop update drops or renames it: closing the pane would then disable the whole plugin.

---

## KI-16. Desktop sends a "stacked skill bundle" (Fixed)

**What happened.** The Learn page's Start button produced Hermes's stacked-skill format (`"/learnloop:study /learnloop:study" stacked skill bundle`, topic on a `User instruction:` line) instead of the single-skill format the hook matched. No lesson started; the model got "No active lesson" from `learn_ask`.

**Fix.** The hook recognises both formats by our own skill body's heading (`# learnloop lesson: start`, `# learnloop practice: start`) inside a Hermes scaffold, and reads the topic from either header (`core._invocation`, tests in `test_core.py`).

---

## KI-17. Reloading learnloop's code (Dev note)

Three halves, three reloads:
- **Hooks and tools** live in the gateway: `hermes -p <profile> plugins disable learnloop && hermes -p <profile> plugins enable learnloop` applies them to new sessions. Headless `hermes chat` runs go through the running gateway too.
- **Dashboard API** (the cards' and pane's routes) lives in each profile's plugin host: `tools/reload_hosts.sh`.
- **Desktop half** (`desktop/plugin.js`): Capabilities → Plugins → Rescan.

---

## KI-18. The model can go around learnloop with general tools (Open)

**What happened.** In chat `local-5c1370cf…` (KI-16), after `learn_ask` said "No active lesson", the model inspected the plugin with `terminal` and `read_file`; the lesson appeared in the database a minute later, most likely created by the model calling learnloop's store from Python. In run `p1-flash` (stale gateway, KI-17) it spent 26 terminal calls diagnosing the missing tools.

**Why it matters.** learnloop's guarantees (grade first, one open question, the practice pause) hold for its tools, not for a model with a shell. The lesson guard blocks skills and memory only.

**Revisit when.** It happens with a working setup. Option: extend the guard to refuse `terminal`/`execute_code` calls that mention `plugin-data/learnloop` during and right after a refused learnloop call.

---

## KI-19. Desktop compiles Tailwind from its own sources (Mitigated)

**What happens.** A class in `plugin.js` works only if Desktop's own source uses the same class; others silently do nothing (the graph's detail card rendered see-through). **Mitigation:** `tests/test_desktop_classes.py` fails on any class Desktop never compiles; the rest is inline styles and a small scoped stylesheet (`STYLE` in `plugin.js`).

---

## KI-20. The answer hook acts for the focused chat (Accepted)

**What happens.** The question dock turns the message box into "Your thinking": a composer middleware rewrites the typed text into the answer when a question is open. Hermes doesn't tell a middleware which chat's composer it runs for, so it acts for the **focused** chat's open question. With two chats side by side, typing in the unfocused one while the focused one has an open question would be taken as that question's answer.

**Mitigation.** Desktop focuses the chat you type in, so this needs an unusual layout. Slash commands always pass through.

**Revisit when.** Hermes passes the session to composer middleware.

---

## KI-21. A card that loaded could show "wasn't created properly" (Fixed)

**What happened.** In a webapp lesson (11 Nov, Opus 5.5), the chat card for an answered question switched to "This question wasn't created properly" while the model was replying. After a page reload both card requests returned 200 and the card rendered normally.

**Cause.** The card polls its question every few seconds. One failed request (the plugin host busy during the model's turn) set the card's error, and the error was never cleared, so a real question was shown as malformed.

**Fix.** Question and problem cards keep showing what they loaded; only three failures in a row on a card that never loaded show the error, and a first load that fails is retried.

---

## KI-22. The dock stayed on "waiting for the verdict" after a free-text answer (Fixed)

**What happened.** Recording the demo (11 Nov, Opus 5.5), a written answer was graded "partial" in the database, but the dock kept showing "Answer sent: waiting for the verdict." until the page was reloaded.

**Cause.** The dock shows the last answer's result from its own store. Multiple choice is graded on submit, so the store already had the verdict; a free answer is graded later by the model, and nothing refreshed the store.

**Fix.** While the dock shows a result without a verdict, it fetches the question every 3 s (up to 3 minutes) and shows the verdict as soon as it lands.

---

## KI-23. The lesson map dialog cut off steps at the right edge (Fixed)

**What happened.** On a 10-step plan in a 1500 px window with the lesson pane open, the map dialog clipped the rightmost step.

**Cause.** The full map was drawn at its natural pixel width inside a dialog capped at 86vw, so a wide plan overflowed.

**Fix.** The map area has a set width (820 px, or 80vw on small windows) and the map scales down to fit it, never past its natural size.

---

## KI-24. Graph region labels could overlap when zoomed out (Fixed)

**What happened.** On the Learn page, with several lessons and an imported group, two region labels were drawn on top of each other.

**Cause.** Labels are drawn at screen size above each region, so a fitted (zoomed-out) graph puts them closer than their text is wide; and regions were sized without regard to their label's width.

**Fix.** Regions are at least as wide as their label. Labels are placed biggest region first; a label that would overlap another moves up a line or below its region.

---

## KI-25. Fractions showed as raw LaTeX in the learner's answer line (Fixed)

**What happened.** An option such as `$\dfrac{V}{c^2}$` appeared in the learner's own chat line as `\dfrac{V}{c^2}`; Desktop shows user messages as plain text.

**Fix.** `plain_math()` turns `\frac` / `\dfrac` / `\tfrac` into `a/b`, along with the roots, powers and symbols it already handled.
