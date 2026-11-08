# LearnHarness in depth

**Pinned source:** `amosblomqvist/learnharness` @ `LH_SHA = 713377f366771e3e4730e6acd1bc290e0ebc6d6e` (2026-11-04), cloned at `~/Projects/learnloop-ref/learnharness`. Paths below are relative to that repo.
**Learner data:** `~/.config/LearnHarness/data/` (1 chat, "Scaled dot-product attention", 195 messages).
**Licence:** AGPL-3.0 (`LICENSE`, `skills/learnharness/LICENSE`).
**Method:** source read directly. *Inferred* marks anything not seen in code or data.

## How a session flows (one page)

1. **The agent is rebuilt every turn from the saved transcript.** There is no long-lived agent. On each request the server builds one agent from the record and throws it away at turn end (`src/agent/teacher-agent.ts:28-35`). Which agent it builds depends on the transcript: before a successful `probe_done` it's the **prober**, after it the **teacher** (`src/core/phases.ts:7-14,83-88`). Practice sessions are a separate session kind that use the **practitioner** from turn one (`teacher-agent.ts:334-347`).
2. **"Fresh agent" means a new system prompt and tool set on the same history**, not a new conversation. Prober and teacher share one transcript (`teacher-agent.ts:29-31`; `prompts/README.md` "Agents share history, not identical toolsets").
3. **Prompts are composed per role** (`prompts/README.md`; `teacher-agent.ts:77-84`):
   - Prober = `system-prompt.md` + `prober/*` + `shared/*`.
   - Teacher = `system-prompt.md` + `teacher/*` + `shared/*`.
   - Practice = `practice/*` + an allowlist of shared files (voice, accuracy, mental model, formatting).
4. **Probe:**
   - reads earlier sessions (`list_sessions`, `list_propositions`);
   - pins the goal down with `ask_user_question`;
   - lists the "strands" the goal depends on;
   - **binary-searches each strand** with graded questions, one per turn (`prompts/prober/10-probe-doctrine.md`);
   - concludes with `probe_done`, whose arguments *are* a structured assessment: one entry per strand with floor, ceiling, misconceptions and what to build from, plus a summary (`src/core/contracts/probe.ts:47-72`).
5. **Handoff:** `probe_done` is refused while a question is open or if the probe is already done (`src/agent/tools/probe.ts:69-79`). On success it queues an auto-wake, so the teacher's first turn (planning) runs immediately (`probe.ts:36-44,81`).
6. **Plan:** the teacher writes a Mermaid `graph TD` with strict slug ids via `plan_init` (`prompts/teacher/10-planning.md`; validation in `src/agent/tools/mermaid-plan.ts:98,148`). It presents the plan, **ends its turn, and waits for the learner to confirm** (`10-planning.md` "Presenting ends your turn").
7. **Teach:** a cycle of **predict → teach → check** (`prompts/teacher/28-predictions.md`). Every teach question must carry `type` (predict/check) and a `nodeId` matching a plan slug, enforced by the schema (`src/core/question-core.ts:242-284`). The map's position is simply the latest tagged node. Checks render collapsed behind a "Check your understanding" button; predictions render open (`question-core.ts:215-240`).
8. **Questions end the turn structurally.** A successful question call terminates the run (`teacher-agent.ts:136-177,227`). The learner's answer comes back as **that question's tool result**, holding only what the learner added: selection or text, `correct`, `confidence` (0–100), `thinking`, `thinkingWhileReading`, `dontKnow` (`question-core.ts:756-802`).
9. **Graph:** built afterwards by a separate pipeline: extractor → identity auditor → deterministic merge. It runs once enough teacher prose is uncovered (default 4,096 tokens) (`docs/architecture.md` "Knowledge graph and imports"; `src/agent/subagents/extraction.ts`).
10. **Practice:** a separate session. `problem` commits a hidden model solution, then poses the problem. The learner works in a thinking field. `conclude` records the outcome and reveals the solution, then the session **pauses until the learner explicitly asks for the next problem** (`prompts/practice/00-base.md`; `src/agent/tools/practice.ts:90-214`).

## Mechanisms

### L1. Session lifecycle and agent roles

- **What it does:** picks the prober, teacher or practitioner agent per request from transcript events.
- **Where:** `src/agent/teacher-agent.ts:77-84` (compose), `:179-273` (base options), `:283-347` (factories); `src/core/phases.ts:63-100,166-192` (phase fold); `src/agent/prompts/README.md`.
- **How it works:**
  - Phase is folded from events, never stored: probe → plan at the first successful `probe_done` result, plan → teach at the first `quiz`/`explain` call carrying a `nodeId` (`phases.ts:83-97`).
  - Each phase has its own prompt and tool registry. The history is shared.
  - The agent is rebuilt every turn (`teacher-agent.ts:31-34`).
- **What the learner sees:** phase dividers in the transcript (`phases.ts:102-139`).
- **Evidence it mattered:** the prober and teacher behave differently: 25 probe questions, then 1 plan, then 45 teach questions (Task 1.6).
- **Depends on:** L2, L4, L5.
- **Prompt text:** `system-prompt.md` (1,191 chars), the shared base.
- **Port cost:** S. Hermes has one agent per session, but a phase-specific method returned in a tool result reproduces "new prompt, same history" closely. What we **can't** reproduce is a *different tool registry* per phase. All seven learnloop tools are visible in every phase, so the store must enforce phase rules instead.

### L2. Probing

- **What it does:** finds the goal and the edge of the learner's understanding on every strand.
- **Where:** `src/agent/prompts/prober/10-probe-doctrine.md`; `src/agent/tools/probe.ts:49-99`; `src/core/contracts/probe.ts:47-72`.
- **How it works:** read the persistent map → make the goal concrete (`ask_user_question`) → list the strands → bracket each strand with floor and ceiling questions, "enter near the top, not the bottom", jumping up sharply on confident correct answers → `probe_done(assessment{strands[{strand, assessment}], summary})`.
- **What the learner sees:** graded question cards, then a streamed assessment.
- **Evidence it mattered:** strong.
  - 25 probe questions: 14 wrong, 10 right, 1 "don't know". **24 of 25 carried thinking.**
  - The assessment cites his thinking directly, e.g. "got Var(X)=4 … by taking the range 5−1, not the definition, so that answer is not evidence of understanding" (`probe_done` call, message 63).
  - Probing took messages 1–63 before the plan.
- **Depends on:** L3 (confidence/thinking), L7 (reads the map).
- **Prompt text:** 3,588 chars.
- **Port cost:** S for the prompt. The structured assessment needs a `learn_phase`/`learn_probe_done` argument.

### L3. Question mechanics

- **What it does:** graded questions with a hidden answer, a confidence slider, thinking channels and "I don't know".
- **Where:** `src/core/question-core.ts:150-300` (schemas), `:455-530` (answer types, confidence stops), `:756-802` (`compactAnswerForModel`); `src/agent/prompts/shared/20-question-tools.md`, `shared/25-confidence.md`, `shared/16-mental-model.md`; UI in `components/question-dock.tsx`, `confidence-rail.tsx`, `answered-card.tsx`.
- **How it works:**
  - Multiple choice requires 2+ options with stable `value`s, an `explanation` written **before** `correctAnswer`, and `correctAnswer` by value (validated). It may be multi-select.
  - The UI adds "I don't know" itself.
  - The browser shuffles and grades.
  - Free recall ("explain" mechanic) has a committed `correctAnswer` that the model grades against.
  - Confidence is a slider with stops **0/30/50/70/90/100**, default 50, read against chance 1/n (`question-core.ts:495-500`; `shared/25-confidence.md`).
  - There are two thinking channels: `thinking` (about the question) and `thinkingWhileReading` (typed while reading the teaching, attached to checks).
  - The explanation is shown to the learner after answering.
- **What the learner sees:** a dock with options, a confidence slider, thinking fields, a reveal button for checks, and an answered card with the verdict and explanation.
- **Evidence it mattered:** very strong.
  - **11 answers were wrong at confidence ≥ 70**, the "committed misconception" signal the method keys on; 1 was right at confidence ≤ 30.
  - 65 of 69 answers carried thinking; 12 checks carried thinking-while-reading.
- **Depends on:** L5, L2.
- **Prompt text:** 3,195 + 1,095 + 979 chars.
- **Port cost:** M. Confidence as a percentage, `dontKnow`, `explanation`, and two thinking fields all need card and schema support.

### L4. Planning

- **What it does:** a minimal dependency tree from what the learner holds to the goal, shown as a live map.
- **Where:** `src/agent/prompts/teacher/10-planning.md`; `src/agent/tools/plan.ts`, `mermaid-plan.ts:9-160`; `src/core/plan-tree.ts`, `plan-blocks.ts`; `components/plan-window.tsx`.
- **How it works:**
  - Mermaid subset: `slug[title]` nodes and `a --> b` "requires" edges; slugs are lowercase and permanent. Errors are line-numbered so the model can fix them (`mermaid-plan.ts:98,148`).
  - Re-planning is a normal event (`plan_init` again).
  - Position is derived from the latest `nodeId`-tagged question; nodes are never marked "finished".
  - The plan is presented, then the turn ends until the learner confirms.
- **Evidence:**
  - His plan has ~25 nodes, including foundations he lacked (`derivative`, `chain-rule`, `expectation`, `variance`).
  - After 44 teach questions, **16 nodes had been visited and the √d_k node had still not been reached**. That explains why "Session 1" took several sittings.
- **Depends on:** L2, L5.
- **Prompt text:** 5,875 chars.
- **Port cost:** S–M: store the plan, validate slugs, require `nodeId` on teach questions, track position. The live map UI is L.

### L5. Teaching loop

- **What it does:** one reasoning step at a time; predict → teach → check; repair before building.
- **Where:** `src/agent/prompts/teacher/05-method.md` (the two principles: unconditional truths first, "how could I have discovered this?"), `20-teaching.md`, `28-predictions.md`, `30-question-principles.md`; `shared/10-voice.md`, `15-accuracy.md`, `40-formatting.md`; `src/agent/narration-guard.ts`, `src/agent/tools/send-to-user.ts:15`.
- **How it works:**
  - Prose comes first, then the check.
  - A wrong answer resumes teaching.
  - Socratic or expository, chosen per step.
  - Predictions motivate the next step; checks verify it.
  - `send_to_user` and the narration guard are a **Claude-specific delivery workaround** (`send-to-user.ts:15`), not part of the method.
- **Evidence:** 45 teach questions (15 predict, 30 check). The learner: "it uncovered a lot of deficiencies I had and worked me through them".
- **Depends on:** L3, L4.
- **Prompt text:** 6,248 + 5,114 + 2,430 + 1,658 chars (+ shared voice, accuracy, formatting).
- **Port cost:** S for the prompt. The collapse-behind-a-button reveal is UI (M).

### L6. Practice

- **What it does:** retrieval practice from the inactive state: recall, discrimination and composition modes, interleaving, a hint ladder, then a pause.
- **Where:** `src/agent/prompts/practice/00-base.md` (5,569), `10-doctrine.md` (14,869); `src/agent/tools/practice.ts:54-214`.
- **How it works:**
  - `problem(statement, modelSolution, target?)` is refused while another problem is active (`practice.ts:139`).
  - `conclude(outcome ∈ {solved, solvedWithHints, movedOn, surrendered}, verdict)` reveals the committed solution (`practice.ts:166-214`).
  - After `conclude`, the turn ends, and the next problem comes only on an explicit "Next problem".
- **Evidence:** none. The session has no practice yet.
- **Depends on:** L7 (picks propositions as material).
- **Prompt text:** 20,438 chars (largest).
- **Port cost:** M (`problem`/`conclude` protocol + pause).

### L7. Knowledge graph

- **What it does:** propositions (nodes) and jointly entailing chains (premises → conclusion), with provenance back to messages.
- **Where:** `src/agent/subagents/extraction.ts` (1,452 lines: instructions `:404-470`, validation `:313-337`, pipeline `:803+`); `src/core/graph.ts` (ancestry `:305-330`); `src/core/chains.ts`; `src/core/coverage.ts`; `skills/learnharness/references/data-format.md`.
- **How it works:**
  - Automatic extraction batches uncovered teacher prose (threshold 4,096 tokens).
  - The extractor proposes anchored propositions and chains.
  - The auditor links identities.
  - A deterministic merge dedupes and simplifies.
  - Coverage ledgers mark processed text.
  - Prober and practitioner can read the graph; **the teacher can't** (`docs/architecture.md`).
- **Why the cycle got in:**
  - Chain validation rejects only a chain whose conclusion is also one of its own premises (`extraction.ts:323-325`).
  - Nothing checks whether a new chain closes a loop with chains already in the graph, so A ⇒ B in one batch and B ⇒ A in another is accepted.
  - Their own comment says "a cycle cannot be minted by the extractor" (`graph.ts:315-317`), which the session's data disproves: `Value vectors → Values don't affect weights → Value vectors`.
  - *Inferred:* identity merging by the auditor can also turn two distinct propositions into one and close a loop.
- **Evidence:** 52 propositions, 41 chains, 11 foundations, 1 cycle. The graph reached into calculus (derivative, chain rule).
- **Port cost:** L for the full extract + audit pipeline. S for model-written records with a real acyclicity check.

### L8. Background jobs

- **What it does:** research, PDF reading, interactive demos and annotated visuals, run as workers whose results are delivered back mid-lesson.
- **Where:** `src/agent/subagents/runner.ts`, `researcher.ts`, `demo-builder.ts`, `visual-maker.ts`, `pdf-reader.ts`; `src/agent/tools/jobs.ts`; prompts `teacher/40-jobs.md` (2,422), `50-demos.md` (3,026), `55-images.md` (1,512).
- **Evidence:** 1 demo and 1 visual in 195 messages.
- **Port cost:** L. Hermes already has web, browser and image tools the agent can use directly.

### L9. Context and compaction

- **What it does:** a custom compaction summary that keeps the learner model and **the plan tree verbatim**.
- **Where:** `src/core/compaction.ts:27-37,344-390`; `docs/compaction-accounting.md`.
- **Port cost:** S. Hermes compacts itself; we keep the plan, open question and probe assessment in the DB and re-inject them every turn.

### L10. Learner files and images

- **What it does:** read-only file tools; show and annotate the learner's images.
- **Where:** `src/agent/tools/read.ts`, `learner-image.ts`; `prompts/shared/30-learner-files.md` (376).
- **Port cost:** none. Hermes has file tools.

### L11. Their bundled agent skill

- **What it does:** lets an external agent read LearnHarness sessions and the graph.
- **Where:** `skills/learnharness/SKILL.md`, `scripts/{_data,graph,sessions}.py`, `references/data-format.md`.
- **Use for us:** a documented format for **importing an existing LearnHarness graph** (nodes.jsonl: `id, name, statement, aliases, createdAt, provenance`; chains.jsonl: `id, premises[], conclusion, provenance`). Port cost **S**, and the importer must run our cycle check.

## Prompt inventory (chars, `wc -c`)

| File | Chars | Purpose | LH tools/UI named | Draft verdict |
| --- | --- | --- | --- | --- |
| `system-prompt.md` | 1,191 | philosophy: measure → plan → teach; absorb logistics | none | Take |
| `shared/10-voice.md` | 1,320 | no praise, no softening | none | Take |
| `shared/15-accuracy.md` | 1,107 | verify before teaching | none | Take |
| `shared/16-mental-model.md` | 979 | thinking fields are primary data | thinking fields | Adapt (wording) |
| `shared/20-question-tools.md` | 3,195 | option craft, free-recall grading, thinking channels, one question per turn | quiz/explain, ask_user_question | Adapt |
| `shared/25-confidence.md` | 1,095 | reading confidence against chance | slider, `dontKnow` | Take (if we keep % confidence) |
| `shared/30-learner-files.md` | 376 | file tools | read/find/grep | Drop |
| `shared/40-formatting.md` | 1,726 | markdown, LaTeX, callouts, mermaid | none | Take |
| `prober/10-probe-doctrine.md` | 3,588 | binary-search probing | list_sessions, probe_done, read, pdf, research | Adapt |
| `teacher/05-method.md` | 6,248 | the two principles | none | Take |
| `teacher/10-planning.md` | 5,875 | minimal tree, map, re-plan, present + confirm | plan_init, nodeId | Adapt |
| `teacher/20-teaching.md` | 5,114 | one step at a time, Socratic/expository, reveal pacing | quiz, button | Adapt |
| `teacher/28-predictions.md` | 2,430 | predict vs check | type, button | Adapt |
| `teacher/30-question-principles.md` | 1,658 | what a check must be | none | Take |
| `teacher/40-jobs.md` | 2,422 | research/PDF jobs | research, pdf | Drop |
| `teacher/50-demos.md` | 3,026 | interactive demos | demo | Drop (unless scoped) |
| `teacher/55-images.md` | 1,512 | images and visuals | visual, show_image | Drop |
| `practice/00-base.md` | 5,569 | practice mechanics, pause law | problem, conclude, Next problem | Adapt |
| `practice/10-doctrine.md` | 14,869 | retrieval-practice theory | none (mostly) | Take |

**Composed sizes:**

- Prober ≈ **14.6k**.
- Teacher ≈ **39.3k** in full, ≈ **32k** after dropping jobs, demos, images and files.
- Practice ≈ **25.6k**.

All fit Hermes's 100k tool-result limit (`hermes-capabilities.md`). The teacher fits a 36k budget only after the drops.

Tool names found in prompt text: `ask_user_question` ×7, `read` ×5, `plan_init` ×5, `quiz` ×4, `problem` ×4, `visual` ×3, `probe_done` ×2, `research` ×2, `pdf` ×2, `explain` ×2, `show_image` ×2, `list_sessions`, `list_propositions`, `demo`, `ls`, `grep`, `find` ×1 each.

## Tool inventory

| Tool | Role | Key parameters | Result to model | Gates |
| --- | --- | --- | --- | --- |
| `probe` (quiz schema, no type/nodeId) | prober | question, options[{label,value}], explanation, correctAnswer, multiSelect | the learner's answer record | one question per turn; ends the turn |
| `recall`/`explain` | prober / teacher (free-recall mechanic) | question, correctAnswer (+type, nodeId when teaching) | the answer record | same |
| `quiz` | teacher | **type**, **nodeId**, + quiz base | the answer record | nodeId must match a plan slug |
| `ask_user_question` | all | question, options?, multiSelect | the choice or text | ends the turn |
| `probe_done` | prober | assessment{strands[], summary?} | fixed ack | refused if a question is open or already done; queues the teacher wake |
| `plan_init` | teacher | mermaid | ok or line-numbered errors | slug grammar |
| `problem` | practice | statement, modelSolution, target? | posed | one active problem; ends the turn |
| `conclude` | practice | outcome, verdict | reveal | requires an active problem |
| `list_sessions`, `list_propositions` | prober, practice | — | graph/session listings | graph switches |
| `research`, `pdf`, `demo`, `visual`, `show_image` | teacher | — | job dispatch | toggles |
| `read`, `ls`, `find`, `grep` | all | — | file content | read-only, sensitive-path guard |
| `send_to_user` | Claude models | text | — | Claude-only delivery workaround |

## A LearnHarness session, measured

- 195 messages; only 4 user messages (all empty text: answers arrive as tool results).
- Probe: 25 questions (14 wrong / 10 right / 1 don't-know), messages 1–63, then 1 `ask_user_question` (goal scope) at 59, `probe_done` at 63, `plan_init` at 69, first teach `quiz` at 78.
- Teach: 44 answered questions (28 right / 13 wrong / 3 don't-know), 15 predict + 30 check.
- 16 plan nodes visited, in order: `token-context → weighted-sum → dot-geometry → relevance → score-matrix → weight-rules → exp-facts → softmax → softmax-scale → row-softmax → readout → raw-attention → qkv → batch → chain-rule → saturation`. The variance strand and `√d_k` are not reached yet.
- Calibration signal: 11 answers wrong at confidence ≥ 70.
- Thinking: on 65/69 answers; thinking-while-reading on 12 checks.
- Graph: 52 propositions, 41 chains, 1 cycle.

### What worked (from the record)

1. **The probe read his reasoning, not his answers.** It discounted a correct Var(X)=4 because his thinking showed he used the range (`probe_done` assessment, msg 63).
2. **The plan went below the goal** to the foundations he lacked: matrix product → dot product, derivative → chain rule, expectation → variance (`plan_init`, msg 69).
3. **Confident misconceptions were caught early:** 11 answers wrong at ≥ 70 % confidence, each followed by teaching (e.g. msgs 79, 117).

### Friction (from the record)

1. **Length:** 63 messages before the plan, and 44 teach questions without reaching the goal node. Great depth, but the goal can't be reached in one sitting.
2. Scope question at msg 59: the goal-scoping question was over the learner's head (`probe_done` summary).
3. Explanations shown after each answer "may have influenced later answers" (the prober's own note in `probe_done`).

## Mechanism → experience matrix (the learner's answers)

| ID | Mechanism | Learner noticed it? | Would the lesson have failed without it? |
| --- | --- | --- | --- |
| L1 | separate prober/teacher | yea | I think so yes |
| L2 | binary-search probing + assessment | yes I noticed the question getting harder and easier to a point where it felt like I started to scratch the limit of my understanding | probably, the agent will just begin spitting out information without about my understanding |
| L3 | confidence slider | I think it's a nice addition especially with the fact that I answered a lot of questions with high confidence but wrong answer, which shows the agent my blindspots | I don't think "failed", rather just progressed slower with the agent taking a long time to spot blindspots |
| L3 | thinking + thinking-while-reading | Oh yes, this is such a huge addition | Again it wouldn't fail, but it wouldn't induce the learning process the LearnHarness designer talked about. Having my thoughts available to the agent shows it my thinking process and allows it to spot any mistakes in my reasoning and target them in order to make me reason correctly |
| L3 | "I don't know" + explanation after answer | yep | yes. This allows the agent to introduce ideas that are unknown to me, or polish my thinking process |
| L4 | live plan map | Yes | It's a very nice addition, since I found myself looking a bunch of times at the map to see where I am |
| L4 | confirming the plan before teaching | yes | It wouldn't fail, but it might've suffered from scope creep, or even underscoping the lesson |
| L5 | predict → teach → check | yes | Yes |
| L5 | checks collapsed behind a button | no? idk what are you talking about | |
| L6 | practice sessions | I haven't tried those yet | |
| L7 | knowledge graph view | Yes | It's a really pretty way to show the topics you practiced, it like a map for the brain so it allows you to maybe spot any blank in there |
| L8 | demo / visual | yes | Not necessarily fail, but it greatly helps in learning, plus hermes already has something similar if I'm not mistaken |

## Design consequences for learnloop (input to `docs/scope.md`)

1. **The question protocol is the product, more than the prose.** Confidence (0–100 with stops), `dontKnow`, a hidden `explanation`, `thinking` and `thinkingWhileReading` all appear in the session data and drive the method. The baseline plan's 1–5 confidence and single thinking box are **too thin**: match LearnHarness.
2. **Predict vs check, and `nodeId` on every teach question.** The baseline has only `check`. Add `type` and `nodeId` (validated against plan slugs) and track plan position.
3. **Probe conclusion = structured assessment.** `learn_phase(teach)` must take `assessment{strands[{strand, assessment}], summary}` in addition to the plan. It's stored and re-injected, giving the teacher what LearnHarness's handoff gives it.
4. **Confirm the plan before teaching.** The teach method instructs the model to present and stop. No code needed.
5. **Turn-ending can't be enforced in Hermes.** LearnHarness ends the run structurally after a question; a plugin can only instruct. Mitigation: the single-open-question rule in the store, plus the instruction in the tool result.
6. **One agent instead of rebuilt agents loses per-phase tool sets.** The store enforces phase rules (probe questions have no `nodeId`, teach questions must have one; practice requires `problem`/`conclude`-style state).
7. **Graph:** model-written plus a real acyclicity check fixes their known bug. Their post-hoc extractor is the larger, better product: Later.
8. **Practice** is a distinct protocol (hidden model solution, outcome enum, pause). Not yet tried, so it's the first candidate for Later.
9. **Import of his existing graph** is cheap (L11) and gives a strong demo: "my LearnHarness knowledge, now available in every Hermes chat".

## Self-check (Task 1.11)

- [x] L1–L11 filled, each with a "Where".
- [x] Prompt inventory covers all 19 prompt files.
- [x] Claims cite path:line or message index; inferences are marked.
- [x] Opens with LH_SHA.
