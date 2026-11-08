# Hermes plugin capabilities for learnloop

Sources, all read on 8 Nov 2026:
- docs at `NousResearch/hermes-agent@e075441` (`~/Projects/learnloop-ref/hermes-agent-docs/website/docs/…`);
- installed build `v0.23.0+209 (90d6b98)` (`$HW` = `~/.hermes/installs/e00cfdc438b1ed6d/environments/376dc4c4a21c40b4ab37e3ad15091b93/workspace`);
- release tag `v0.23.0` (`~/Projects/learnloop-ref/hermes-v0.23.0`, tag commit `2bd378e`).

Doc paths below are relative to `website/docs/`. *Unverified* items are spike checks (see `spike-results.md`).

## Part 1: capability inventory

| Surface | What it allows | Hard limits | Installed | v0.23.0 | Catalog constraint | learnloop use |
|---|---|---|---|---|---|---|
| `ctx.register_tool` | model-callable tool; `handler(args, **kwargs) -> str` (`$HW/tools/registry*.py:988`) | Result over **100,000 chars** spills to `cache/spillover` as preview + path. Per-turn aggregate is **200,000**. Both scale down for small-context models (`$HW/tools/budget_config.py:13-14,57-60`) | ✅ | ✅ | R6: declare in `provides_tools` | 7 lesson tools; carries the phase method |
| `pre_llm_call` hook | returns `{"context": str}`, appended to the **current user message**, ephemeral, not persisted (`developer-guide/plugins/index.md` § pre_llm_call) | **10,000 chars per hook**, then spills to `hook_outputs/` (`$HW/tools/hook_output_spill.py:5`); 30 s timeout, fail-open (`plugins.hook_callback_timeout`) | ✅ | ✅ (`hermes_cli/plugins_dispatch.py:44`) | R6: `provides_hooks` | per-turn reminder + lesson state; recall in other chats |
| `post_compaction` hook | `session_id, old_session_id, kind, …` | bounded hook (same timeout) | ✅ | ✅ (`plugins_dispatch.py:51,56`) | R6 | rebind lesson to the new session id |
| `post_llm_call` hook | sees `assistant_response` once per successful turn | bounded, fail-open | ✅ | ✅ | R6 | (later) post-hoc graph extraction |
| `register_system_prompt_section` | fixed text frozen into each new session prompt | **4,000 chars max** (`$HW/hermes_cli/plugins_dispatch.py:99-100`); 32 sections; an oversize section is **skipped silently**, not truncated | ✅ | ✅ | none | not used (too small; can't change per phase) |
| `ctx.register_skill` | `skill_view("learnloop:x")` loads a bundled SKILL.md; read-only; not listed in the prompt index (`index.md` § Bundle skills) | loaded through a normal tool result, so the 100k limit applies | ✅ | ✅ | none | fallback channel for method text |
| `ctx.register_command` | `/learn …`; handler gets `raw_args` (+ `session_id`, `platform`, `source` kwargs); returns text (`index.md:1786-1860`) | can't start a model turn; built-in names win | ✅ | ✅ | none | `/learn` start/status/graph |
| `ctx.ask_choice` | picker from a **sync slash-command handler** only | returns `None` in hooks, cron and async handlers (`index.md` § Ask the user) | ✅ | ✅ | R12 | not used |
| `ctx.dispatch_tool` | call any tool from a command or hook with the parent context | in the gateway, the parent agent degrades | ✅ | ✅ | none | (later) cron for spaced practice |
| `ctx.llm.complete[_structured]` + `register_auxiliary_task` | host-owned LLM calls on the user's model, or on a user-configurable aux slot (`developer-guide/plugin-llm-access.md`) | `provider=`/`model=` overrides denied by default | ✅ | ✅ | R11 satisfied (no keys) | (later) extractor + auditor |
| `config_schema` + `ctx.get_config` | settings rendered as a Desktop form | types str/int/bool/list/dict/secret | ✅ | ✅ | none | `card_mode`, `recall_in_chats` |
| `plugin_db` / `plugin_data_dir` | `<HERMES_HOME>/plugin-data/<name>/data.db` (WAL), survives update/remove, profile-scoped | — | ✅ (`$HW/plugins/plugin_storage.py:27-45`) | ✅ | none | the store |
| `get_session_env("HERMES_SESSION_ID")` | session id inside a tool (public seam) | must equal the hook's `session_id` (*unverified*, U2) | ✅ (`$HW/gateway/session_context.py:40-90`) | ✅ (line 43) | R9 allows this one name | lesson binding |
| Desktop `TRANSCRIPT_DIRECTIVE_AREA` | the model writes a paragraph `::name{k="v"}`; the plugin renders a component inline; `render({attrs, sessionId, streaming})` (`developer-guide/desktop-plugin-sdk.md:1100-1180`) | the directive must be the whole paragraph; attrs are untrusted strings; first registration of a name wins | ✅ (used by core `::preview`) | ✅ (`apps/desktop/src/lib/transcript-directives.ts`, `sdk/index.ts`) | R8: SDK-only imports | answer card |
| `host.composer.submit(sessionId, text)` | sends a user turn into **that** chat; returns `false` if it has no visible composer (`desktop-plugin-sdk.md:1120-1145`) | — | ✅ (the `quota` plugin calls it, `~/.hermes/desktop-plugins/quota/plugin.js`) | ✅ (`apps/desktop/src/sdk/index.test.ts`) | R8 | card submits the answer |
| `dashboard/plugin_api.py` → `ctx.rest` | FastAPI router at `/api/plugins/<id>/`, imported only when the plugin is enabled in `config.yaml` (`desktop-plugin-sdk.md:2234-2280`) | runs in the gateway process | ✅ | *unverified* | R8 reviewers read it | card fetches the question without the answer key |
| Desktop panes/routes/sidebar | full React panes (`desktop-plugin-sdk.md:257-330`) | `jsx()` calls only, no JSX syntax | ✅ | ✅ | R8 | (later) graph view |
| `ctx.files` | the plugin's own folder + user-granted folders (`desktop-plugin-sdk.md:1613-1680`) | — | ✅ | *unverified* | R8 prefers it over the raw bridge | (later) Obsidian export |
| `::preview` widget + `data-hermes-send` | sandboxed HTML that can send a hidden user turn | **500 chars**, 1/s (`desktop-plugin-sdk.md:1160-1180`) | ✅ | ✅ | none | card fallback if directives fail |
| built-in `clarify` tool | model asks the user ≤ 4 choices + Other | no confidence/thinking fields; subagents can't call it | ✅ | ✅ | — | not used (too narrow) |
| `ctx.register_rpc`, `ctx.emit_to_session` | frontend RPC | — | ❌ absent in the installed build | — | — | don't use |
| Memory provider / context engine plugins | replace Hermes memory or the compressor | **exclusive** slots (one active) (`developer-guide/memory-provider-plugin.md`) | ✅ | ✅ | — | not used: would displace the user's own memory setup |

## Part 2: answers

**Q1. Long instructions (~30k chars per phase).**
- **Tool results are the channel.** They pass intact up to 100k (200k per turn), so a 36k method returned by `learn_start`/`learn_phase` arrives whole (U7 confirms it live).
- `pre_llm_call` (10k, replayed and paid every turn) and system-prompt sections (4k, silently skipped above that) are both unusable for it.
- A plugin skill (`skill_view("learnloop:teach")`) also works, but costs the model an extra decision.
- **What survives:** normal compaction summarises older turns, so the method text can be lost in a long lesson. Proactive tool-result pruning is **off by default** (`compression.proactive_prune_tokens: 0`, `$HW/hermes_cli/config_defaults.py:602`). When a user enables it, results over 8,000 chars outside the protected tail get summarised. **Mitigation:**
  - the per-turn reminder tells the model to call `learn_method` when the method is gone;
  - lesson state lives in the DB and is re-injected every turn.

**Q2. Agent roles / fresh-agent handoff.**
- `delegate_task` children can't talk to the user (no `clarify`, and their results come back as summaries), so a "prober subagent" can't run an interactive probe.
- `/new` drops the chat.
- **Recommendation: one agent, with the method swapped through `learn_phase` results.** LearnHarness's fresh-agent reason is a clean context for the teacher. We get part of that by sending a compact probe summary (graded probe answers) with the teach method.

**Q3. Question UI.**
- **Transcript-directive card + `composer.submit`:** supports options, confidence and thinking. Desktop only. **This is the primary UI.**
- **Text mode:** works on every platform (CLI, Telegram). **This is the fallback.**
- `clarify`: max 4 options, no confidence or thinking.
- `ask_choice`: slash commands only.
- `::preview` widget: 500-char send cap, but it works as a backup card.
- Telegram inline buttons via platform handlers: possible but heavy. Later.

**Q4. Answer key.** It stays in SQLite. `learn_ask` returns only the question id; the card reads `/questions/{id}`, which omits `correct`; multiple choice is graded server-side in `learn_grade`. The model knows the key, because it wrote the question, but it never reaches the learner's screen before they answer.

**Q5. Post-hoc graph extraction.**
- Feasible: `post_llm_call` sees each assistant reply, and `ctx.llm.complete_structured(task="learnloop-extract")` can extract propositions on a user-configurable aux model.
- But hooks are bounded at 30 s and fail open, so extraction would need its own thread (*unverified* that threads started from hook callbacks are safe), and every turn adds an aux LLM call.
- **Recommendation: Later.** In v0.1 the teaching model records facts with `learn_record`.

**Q6. Graph viewing.** `/learn graph` text listing in v0.1. A Desktop pane with a node list is ~2–3 h (later). Export to Obsidian via `ctx.files` is later.

**Q7. Spaced practice.** A plugin can call `ctx.dispatch_tool("cronjob", …)` from a command to schedule a job delivered to Telegram (*unverified* for plugin-created jobs). Later.

**Q8. Compaction.** The session id changes, which the `post_compaction` rebind handles. Older turns get summarised, which `learn_method` reload covers. Nothing lets a plugin pin text against compaction, apart from re-injecting it every turn (capped at 10k).

**Q9. Platform detection.** `get_session_env("HERMES_SESSION_PLATFORM")` in tools, and `platform` in hooks and commands. Desktop vs CLI values are *unverified* (U3); the `card_mode` setting covers a failure.

**Q10. Limits.**
- Tool results: 100k / 200k per turn.
- Hook context: 10k per hook.
- Hook timeout: 30 s (max 600).
- System section: 4k.
- `data-hermes-send`: 500 chars.
- Desktop module eval: 10 s.

## requires_hermes floor check (plan Task 3.2)

All grepped in the `v0.23.0` tag tree:

| Symbol | Found at |
|---|---|
| `register_tool`, `register_hook`, `register_command`, `get_config` | `hermes_cli/plugin_validate.py` (+ plugins.py) |
| `plugin_db` | `plugins/plugin_storage.py` |
| `get_session_env`, `HERMES_SESSION_ID` | `gateway/session_context.py:43` |
| `pre_llm_call`, `post_compaction` | `hermes_cli/plugins_dispatch.py:44,51` |
| `register_system_prompt_section`, `register_auxiliary_task`, `dispatch_tool` | `hermes_cli/plugins.py` |
| `TRANSCRIPT_DIRECTIVE_AREA` | `apps/desktop/src/lib/transcript-directives.ts`, `apps/desktop/src/sdk/index.ts` |
| `composer.submit` | `apps/desktop/src/sdk/index.test.ts` |

**Verdict: `requires_hermes: ">=0.23.0"` is truthful.** The Desktop card is feature-detected anyway.

## Spike checks still needed (live)

U1 hook injection reaches the model; U2 tool and hook session ids match; U3 platform values; U4 card renders and `composer.submit` lands in the right chat; U5 `ctx.rest` reaches `plugin_api.py`; U6 SQLite across threads; U7 a 40k tool result arrives intact.
