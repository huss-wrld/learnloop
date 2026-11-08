# Compliance checklist (catalog rules + hackathon)

Phase 0 decisions (8 Nov 2026): name `learnloop`; **no blanket commit approval: show every diff first**.


| Item | How learnloop complies | Verified by | ✅ |
|---|---|---|---|
| R2 SHA pin | entry pins full 40-char HEAD of the release commit | `git rev-parse HEAD` length 40 | |
| R3 no self-update | no network code anywhere | `grep -rnE "urllib|requests|httpx|socket|subprocess" --include=*.py . | grep -v tests/` → empty | |
| R6 capabilities match | plugin.yaml + entry list 7 tools, 2 hooks | `hermes plugins doctor . --ci` exit 0 | |
| R7 security scan | stdlib + fastapi only | `hermes plugins validate . --install-deps` no FAIL | |
| R8 desktop surface | imports only sdk/react/jsx-runtime; no eval, no document.*, no window.hermesDesktop | `grep -nE "import |eval|new Function|document\.|hermesDesktop" desktop/plugin.js` shows only the 3 imports | |
| R9 public API only | Hermes imports: plugins.plugin_storage, gateway.session_context.get_session_env | validate shows no private-import warnings | |
| R10 deps | none declared | no python_dependencies, no pyproject.toml | |
| R11 credentials | none used | grep for get_secret/env reads → empty | |
| R12 unattended | no blocking calls; hooks return within ms; tools never wait for a human | code review of hook.py, tools.py | |
| R13 disclosure | README "What this plugin does on your machine" section + PR body | README present at pinned SHA | |
| R14 requires_hermes | ">=0.23.0" in plugin.yaml and entry; symbols exist at v0.23.0 (Task 3.2) | `docs/research/hermes-capabilities.md` § floor check | ✅ |
| R17 no binaries | text files only | `git ls-files | xargs file | grep -viE "text|json|empty"` → empty | |
| A1 AGPL obligations | LICENSE = full AGPL text; NOTICE names LearnHarness + LH_SHA; every method/*.md starts with a source/modification comment; README credits | `grep -c 'GNU AFFERO' LICENSE` ≥ 1; `head -6 method/*.md` shows headers | |
| H1 PR to catalog | plugin-catalog/learnloop.yaml PR open | PR URL | |
| H2 demo < 90 s on X tagging @NousResearch | maintainer posts | post URL, duration | |
| H3 form submitted | https://form.typeform.com/to/FwJLvOln | confirmation screen | |
| H4 deadline | before Wed 11 Nov 23:00 CET | timestamp | |
