# Sentinel AI — TODO

Priority-ordered. Evidence in parentheses is from a survey of the codebase on
2026-08-11, so re-check the counts before trusting them.

---

## 1. Paid API calls bypass every guardrail outside the chat panel  ⚠️

**22 sites construct a `ChatWorker` directly; there is 1 `validator.validate`
call and 0 usage-tracking calls in the whole app.**

Only `send_prompt()` (the chat panel's Send button) runs the guarded sequence:

    estimate cost → validator.validate (budget) → confirm_external_api_request
    → run_logger.start → ChatWorker → log_request + save_chat + run_logger.finish

Every other runner (`osint_analyse`, `roi_analyse`, `health_analyse`,
`inv_analyse`, `nfl_bet_analyse`, `music_analyse`, `webdesign_generate`,
`wifi_run`, the author/manuscript generators, …) picks a provider that may be a
paid one and calls `ChatWorker` directly. Consequences:

- the €1 session / €5 daily caps do not apply to most of the app;
- "Cost Today" and "Requests Today" stay at 0 no matter what those agents spend;
- no confirmation prompt before spending money;
- nothing is written to Saved Chats (which is why every saved chat is `chat:`).

**Fix:** two helpers on `GodAI`, and every runner calls them —

- `authorize_request(agent, tool, provider, model, prompt) -> bool`
  (estimate → validate → confirm → `run_logger.start`; `False` means blocked)
- `record_request(agent, tool, provider, model, prompt, messages, response, usage)`
  (`log_request` → session totals → `save_chat` → `run_logger.finish`)

This closes four separate defects with one change.

**Status: in progress.**

## 2. `main.py` is 11,401 lines

One file holds 17 agent UIs, routing, cost logic, history and styling. The cost
is concrete: a checkbox-spacing fix had to go in the global stylesheet because
the pattern repeats everywhere, and a card-padding fix touched 6 identical
`setContentsMargins` calls. (`list_models()` ×64, `QGroupBox(` ×57,
`setContentsMargins` ×75, `provider_box.addItems` ×13.)

**Fix:** one module per agent panel (`ui/panels/osint.py`, …) plus a shared
`AgentPanel` base for the provider/model/actions row all 17 rebuild by hand.
Do this *after* #1 — the shared helper makes the seam obvious.

## 3. Other agent panels still crush when the window is narrow

`FlowLayout` (main.py) fixed the chat panel: a `QHBoxLayout` reports the sum of
its children as its minimum width, so a long control row pins an impossible
minimum on the pane and Qt compresses buttons past their own minimums —
labels get chopped to "uto Rout", "ecomme".

Still affected: AuthorPanel (needs 1091px), WiFiPanel (803px), OSINTPanel and
WebdesignPanel (728px each). Mechanical now that `FlowLayout` exists.

## 4. No timeouts on any cloud client

`ollama_client` sets 10s/300s. All five paid clients — `openai_client`,
`deepseek_client`, `kimi_client`, `gemini_client`, `anthropic_client` — pass no
timeout at all. A hung connection freezes that agent with no recovery.
Add a timeout plus one retry on transient errors.

## 5. 14 silent `except: pass` blocks

Failures vanish, including around history loading and model listing — if
`load_history_list` throws, the list is silently empty. At minimum, log to the
run logger.

## 6. Test coverage is inverted

98 passing scenario tests cover agent prompt construction (`pytest tests/`,
0.16s). Nothing covers routing, cost estimation, validation or history — the
money logic is the untested part. Extracting #1 into helpers makes it testable
without a GUI.

---

## Smaller items

- Saved Chats: add an "All agents" filter above the search box. Depends on #1
  (nothing but `chat:` is saved today). `chat_title_from_data` already renders
  any agent generically, and every saved file carries an `agent` field, so it
  works retroactively.
- Kimi prompt caching ($0.19/1M on cache hits, ~80% off input) is not modelled
  in `config/pricing.json`, so estimates for repeated context are conservative.
- `BUDGET` card: `Session €` / `Daily €` could share one row (~34px saved), but
  the two label+field pairs do not fit the sidebar's ~250px inner width without
  shortening the labels.
