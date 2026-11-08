# Spike results (8 Nov 2026, Hermes v0.23.0+209, Desktop)

Session: @session:default/local-4404400743c264fcab56aa87718de989aa31f6ed145022e425855f755e8257e3 ("Identify spike marker"), model deepseek-v4.1-flash.

| Unknown | Result | Decision |
|---|---|---|
| U1 pre_llm_call reaches model | ✅ The model answered `SPIKE-MARKER-7731`. It took the text for part of the user's message, which matches the docs: context is appended to the user turn. | Phase method via tool results, reminder + state via hook, as planned. Phrase injected text as "[learnloop] …" so the model doesn't attribute it to the user. |
| U2 session id source | ✅ Tool `kwargs["session_id"]` == `get_session_env("HERMES_SESSION_ID")` == hook `session_id` (`local-4404…57e3`). | Use `kwargs["session_id"]`, falling back to the env var. |
| U3 platform values | ⚠️ The hook gets `platform="desktop"`, but in the tool `HERMES_SESSION_PLATFORM` is `"local"`. The tool can't tell Desktop from CLI. | The hook stores `platform` per session id in memory; `use_cards()` reads that by session id. `card_mode` setting stays as an override. CLI value still to record (expected not `desktop`). |
| U4 directive + composer.submit | ✅ After the Desktop half was switched on, the button rendered; clicking it added the user turn `spike card clicked n=1 … sessionId=local-4404…57e3` **to the same chat** (msg 12698). Before that, the line showed as raw text: the Desktop half has its **own enable switch**, off by default. | Card design works. README + `/learn` reply must tell users to switch on the Desktop half (Capabilities → Plugins), and text mode covers anyone who doesn't. |
| U5 plugin_api via ctx.rest | ✅ `ping={"ok":true}` from `dashboard/plugin_api.py`. | Card fetches questions from the backend route; answer key never leaves the server. |
| U6 sqlite across threads | ✅ The hook (thread `hermes-hook-hook`) and the tool (`ThreadPoolExecutor-…`) both used the DB with no error. `plugin_db()` returns a **new connection per call** (`plugin_db_cached: false`). | Store opens its **own** connection via `plugin_data_dir()` with `check_same_thread=False` (our Store shares one connection across threads under an RLock). |
| U7 tool-result size | ✅ A ~40k-char result arrived intact (`END-MARKER-5519`). | `METHOD_BUDGET = 36_000` stands. |
| U9 (new) tool visibility | ⚠️ Plugin tools are **deferred** in this setup: the model reached them through `tool_describe` → `tool_call`, not directly. | Every learnloop instruction names the tools explicitly. Upside: deferred tools don't cost prompt tokens in every session. Remaining risk: weaker models skip the lookup, so the `/learn` reply and the reminder say "call learn_ask (via tool_call if needed)". |
