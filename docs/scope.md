# learnloop v0.1 scope

Inputs: `research/learnharness.md` (incl. the mechanism matrix, 8 Nov), `research/hermes-capabilities.md`.
Budget: ~13 h of build for Take + Adapt (deadline: PR open Tue 10 Nov night).

| ID | Mechanism | Value | Evidence | Hermes surface | Feasible | Cost | Verdict | Reason |
|---|---|---|---|---|---|---|---|---|
| L1 | Prober/teacher split | H | matrix: "I think so yes" | method swapped by `learn_phase` result; store enforces per-phase rules | native | 1 h | **Adapt** | LH's "new agent" is a new prompt on the same history; we reproduce that |
| L2 | Binary-search probing + structured assessment | H | matrix: noticed difficulty moving to his limit; 25 probes, assessment quoted his reasoning | prober prompt port; `learn_phase(teach, plan, assessment)` stores strands | native | 1.5 h | **Take** prompt / **Adapt** tools | core of the experience |
| L3 | Full question protocol: confidence %, "I don't know", hidden explanation, thinking + thinking-while-reading | H | matrix: thinking "huge addition"; 11 wrong answers at ≥70 % confidence | `learn_ask` schema + card + text mode | native | 4 h | **Adapt** | baseline (1–5 confidence, one box) is too thin |
| L4a | Plan with slugs, `nodeId` on teach questions, position tracking | H | 16 nodes visited | store + validation | native | 1 h | **Adapt** | needed for the map and predict/check |
| L4b | Confirm plan before teaching | M | matrix: prevents scope creep | prompt only (teach method) | native | 0 h | **Take** | free |
| L4c | Live plan map | M–H | matrix: "looked a bunch of times to see where I am" | Desktop directive card `::learnloop-map` (node list: done / current / next) + `/study plan` text | native | 2 h | **Adapt (simple)** | full mermaid canvas is L; a status list gives the "where am I" |
| L5 | Predict → teach → check | H | matrix: "Yes"; 15 predict + 30 check | `type` + `nodeId` on `learn_ask`; prompt port | native | 1 h | **Take** | |
| L5b | Checks collapsed behind a button | L | matrix: didn't notice | — | — | — | **Drop** | no evidence it mattered |
| L6 | Practice sessions | ? | not tried | `problem`/`conclude` protocol | native | 3 h | **Later** | not yet tried; biggest prompt (20k) |
| L7a | Graph with acyclicity check (model-written) | H | 52 nodes; LH cycle bug | `learn_record` | native | 0.5 h (mostly done) | **Adapt** | fixes LH bug |
| L7b | Post-hoc extractor + auditor | M | — | `post_llm_call` + `ctx.llm` aux task | workaround | 6 h | **Later** | cost + 30 s hook limit |
| L7c | Graph view | M–H | matrix: "a map for the brain" | Desktop pane | native | 3–4 h | **Later (first stretch goal)** | over budget; `/study graph` text in v0.1 |
| L8a | Interactive demos | M–H | matrix: "greatly helps"; 1 demo | Hermes's own `::preview` HTML widgets; adapt `teacher/50-demos.md` | native | 1 h | **Adapt** | Hermes already has this; prompt work only |
| L8b | Visuals / image annotation, research, PDF jobs | L–M | 1 visual | agent's own tools (web, image, files) | native | 0 h | **Drop** as plugin features | Hermes tools cover it |
| L9 | Compaction handling | M | — | DB state re-injected + `learn_method` + `post_compaction` | native | 0.5 h | **Adapt** | |
| L10 | Learner files | L | — | Hermes file tools | native | 0 | **Drop** | |
| L11 | Import existing LearnHarness graph | M | strong demo | importer from `nodes.jsonl`/`chains.jsonl`, cycle-checked | native | 1 h | **Take** | "my LH knowledge, in every Hermes chat" |
| H1 | Recall learned facts in every chat | H (pitch) | — | `pre_llm_call` | native | done | **Take** | the Hermes-native differentiator |
| H2 | Text mode on every platform | M | — | tool result | native | done | **Take** | |
| H3 | `/study` command | M | — | `register_command` | native | done | **Take** | |
| H4 | Spaced practice via cron → Telegram | M | — | cron | unverified | 3 h | **Later** | depends on L6 |

**Take + Adapt total ≈ 13.5 h.** At budget; no slack for L7c graph view.

Decisions (8 Nov 2026):
- **L6 practice: Later.**
- **L7c graph view: Include.** Schedule risk accepted. It's built after everything else, so it's the first thing cut if Tuesday slips.
- **L4c plan map: full Mermaid map, not a status list.** Desktop renders ```mermaid fences natively (`apps/desktop/src/components/assistant-ui/embeds/registry.tsx`) and the SDK exports `MessageTextContent` (`sdk/index.ts:1684`). So a `::learnloop-map` card can render the stored plan with `classDef` styling for done/current/next. Est. 2 h; live check U8.
- **Command name:** `/study`, because `/learn` is a Hermes built-in (skill learning); a plugin command with a built-in's name is skipped silently (`hermes_cli/plugins.py:660`).
- **Opt-in UX (8 Nov):** learnloop is inert until `/study <topic>`. The lesson is bound to that chat only. `/study stop` ends it. **No `learn_start` tool:** only the command starts lessons, so the model can't start one on its own. Recall in other chats is **off by default**, toggled with `/study recall on|off`; when it's used, the reply ends with a small "used learnloop knowledge" note (instruction in the injected context). Commands: `/study <topic> | stop | status | map | graph [words] | recall on|off | import <path>`.
- New total ≈ 17 h against a ~13 h budget: build order puts L7c last.
