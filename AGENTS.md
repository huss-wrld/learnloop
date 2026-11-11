# learnloop

A Hermes Agent plugin that ports LearnHarness's teaching method into Hermes. `/learnloop:study <topic>` runs probe → plan → teach with graded checks. `/learnloop:practice <topic>` drills what you've learned with a hint ladder. Everything learned goes into a per-profile knowledge graph. There are three halves:
- a Python agent plugin: `__init__.py`, `core.py` and `store.py`;
- a Desktop UI: `desktop/plugin.js`;
- backend routes for that UI: `dashboard/plugin_api.py`.

Licence AGPL-3.0-only.

## Layout
- `__init__.py`: `register(ctx)` wires the skills, the 8 `learn_*` tools, 4 hooks and the `/learnloop` command. These must match `provides_tools` / `provides_hooks` in `plugin.yaml`; `hermes plugins validate` checks them.
- `core.py`:
  - tool handlers (`tool_*`), raising `LearnError` for refusals the model sees;
  - per-turn notes (`pre_llm_call`);
  - the `/learnloop` command;
  - skill text assembly.
- `store.py`: SQLite `Store` (lessons, questions, propositions, chains, problems, settings). It's one Store per Hermes home (profile), opened via `plugin_db()`. Data never goes anywhere else, e.g. the user's notes vault.
- `method/*.md`: the teaching prompts, adapted from LearnHarness. Each file has an attribution header naming its sources; keep it. The verbatim originals are in `docs/research/method-raw/`; don't edit those.
- `skills/{study,practice}/SKILL.md`: **generated**. Never hand-edit them; edit `method/` and regenerate.
- `desktop/plugin.js`: a single file that imports only `@hermes/plugin-sdk` and `react` (a catalog rule). It holds the question card and dock, the lesson pane, the plan map, and the Learn page graph.
- `tools/`: dev-only, never loaded by Hermes.
  - `drive.py`: headless scripted lessons.
  - `scorecard.py`: scores a driven run.
  - `reload_hosts.sh`: restarts one profile's plugin host.
  - `build_skill.py`: regenerates `skills/`.
- `docs/known-issues.md` (KI-N entries), `docs/testing.md` (manual live checks), `docs/compliance.md` (catalog and hackathon checklist).

## Build & test
```bash
uvx --with fastapi --with httpx pytest -q -p no:cacheprovider tests   # full suite, ~2 s
hermes plugins validate .                                             # catalog checks (manifest, capabilities, desktop surface)
python3 tools/build_skill.py                                          # after ANY edit under method/ or the skill text in core.py
node --check desktop/plugin.js                                        # quick syntax check; there is no JS build step
```
- Tests import the repo as the package `learnloop` via `sys.path`, so the checkout folder must be named `learnloop`.
- `tests/test_desktop_classes.py` skips unless a Hermes Desktop source checkout exists at `$HERMES_DESKTOP_SRC` (default `~/Projects/learnloop-ref/hermes-v0.23.0/apps/desktop/src`).

## Running it live
- Use a throwaway profile (the repo's convention is `learnloop-test`), never `default`. The plugin is symlinked into `~/.hermes/profiles/<p>/plugins/learnloop`.
- Python changes: `hermes -p <profile> plugins disable learnloop && hermes -p <profile> plugins enable learnloop`, then `bash tools/reload_hosts.sh <profile>`, then Desktop → Capabilities → Plugins → Rescan.
- JS-only changes need only the Rescan (or a page reload in the webapp).
- learnloop's Desktop part must be enabled per profile: Capabilities → Plugins → learnloop.

## Conventions
- Commits: `feat:` / `fix:` / `docs:` / `tools:` / `method:` prefixes. Several scopes in one subject are joined with `; `. Subjects say what changed, not how it was found.
- Every behaviour bug gets a `docs/known-issues.md` entry ("What happened / Cause / Fix", with status in the heading) and a regression test.
- Desktop classes: only Tailwind classes that Desktop itself uses compile (KI-19). Otherwise use inline `style`. `test_desktop_classes.py` enforces this.
- Multiple-choice options are shuffled server-side, seeded by question id. Position-based tests rely on the autouse `fixed_option_order` fixture in `tests/conftest.py`.
- Method rules encoded in prompts and guards:
  - the probe measures and doesn't teach;
  - grade before moving on;
  - one open question at a time;
  - after a miss, step down to a smaller question instead of explaining.

## Pitfalls
- Never run `tools/reload_hosts.sh default`. The default profile's host only returns after a full Desktop restart (the script refuses without `FORCE=1`).
- Never run `hermes gateway restart` yourself; the maintainer does it.
- The composer middleware gets no session id, so the answer hook acts on the focused chat (KI-20, accepted).
- Desktop shows the learner's own messages as plain text. Maths in lines learnloop writes for the learner goes through `plain_math()` in `core.py`.
- The catalog pins a commit SHA. Bump `version` in `plugin.yaml` together with any SHA bump, and never add self-updating code.
- `IDEA.md` is the maintainer's private scratch file: keep it untracked.
