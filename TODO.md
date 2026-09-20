# Imprint — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)

Full reasoning, measurements and verification notes for each item are kept below
under **Detail** — this checklist is the summary view.

**State, September 2026.** Eight agents behind mode tabs; the GUI rebuilt on
`ui/forms.py` over a header bar and two fixed rails; Video and Social shipped,
which closes the last two gaps against the original plan. Every paid path in
the GUI goes through the request guard, including the ones billed per unit
rather than per token — the 2026-09-20 re-analysis found and closed the last
in-app exception (ElevenLabs shorts); the Course Generator CLI remains the one
paid workflow outside it (tracked in agents/course/TODO.md). 704 tests pass in
an isolated database (2026-09-20; isolation now enforced by conftest rather
than per-fixture convention). The installed macOS app is a live launcher into
this source tree; restarting it loads changes.

The package foundation of **Refactor Phase 4** is complete: every agent owns a
repo-ready directory, public API, README, TODO and suggestions file, while one
catalog drives the umbrella roster.  Moving the UI panels and domain-only
services into those packages remains the largest open implementation step.
Music and Site Builder now own their workspace layouts and request/result
lifecycles in their own packages. Audiobook owns its Convert and Listen layout
and listening actions; paid conversion handlers still live on the host. Temporary control
aliases remain in the umbrella for shared integrations.

---

## v2 — current

- [x] `P1` `design` `@ai` **Refactor Phase 3** — `ui/host.py` defines the `AgentHost` protocol (this fork never had it: it landed in Sentinel after the fork point) and `ui/panels/base.py` defines `AgentPanel`, which absorbed the five `*_load_models` methods. Composition, as the entry called for: `GodAI` owns one `AgentPanel` per agent and delegates. Phase 4 (one module per panel) is still open. Original note: — the `AgentHost` protocol and the shared `AgentPanel` base, then one module per agent panel. Phases 1 and 2 shipped (`ui/workers.py`, `ui/widgets.py`, `ui/style.py`, `ui/tooltips.py`, `ui/dialogs.py`). `main.py` was ~10,400 lines when this was written; the "Strip the security verticals" commit (unrelated to this refactor — it deleted six agents' worth of code) has since cut it to ~7,100. Phase 3 itself hasn't started. This is the first phase with a design decision in it: composition over mixins.
- [x] `P1` `bug` `@ai` `_pending_requests` keyed by request token rather than agent name. `authorize_request` returns the token (truthy, so the 11 `if not ...` call sites are unchanged) and an agent name still resolves to that agent's oldest outstanding request.
- [x] `P2` `bug` `@ai` Remove the dead `ops_identity` sidebar entry — it is listed in `agent_titles` with no agent module or panel behind it (gone as of the "Strip the security verticals" commit; not verified as a deliberate fix, but confirmed absent from `main.py` now)
- [x] `P2` `feature` `@ai` Model Kimi prompt caching — `cached_input_per_1m_usd` on the pricing table, captured from the Kimi response and billed at the cached rate. Uncovered a bigger bug while wiring it up: see the pricing-rows item below.
- [x] `P2` `feature` `@ai` **Chat Projects Stage 2** — named context bundles now group saved chats; project instructions enter the system message and the preflight token estimate, defaults apply only when switching projects, and optional per-project daily limits guard tagged spend. Reopened chats retain prior turns for follow-up without leaking old system context across projects; estimates count the retained turns. Settings can create, edit, archive, restore or delete a project while preserving and unfiling its chats. See `docs/projects_roadmap.md`.
- [x] `P3` `design` `@ai` Budget card: `Session` and `Daily` now share one row. The width concern was right — it only fits because the euro sign moved out of both labels and into the card heading (`BUDGET (€)`). Measured, not eyeballed: the row's minimum is 175px and the card's `minimumSizeHint()` 221px, against a right panel that is 260px at its narrowest.
- [x] `P3` `testing` `@ai` Budget comparison switched to `Decimal` — a request estimated at exactly the remaining budget is now allowed, and the test that pinned the float behaviour asserts the flip.
- [ ] `P2` `research` `@me` Decide whether `RunLogger` should grow a general `note` method — it is the tidier home for the `_note_failure` warnings if they ever need to be queryable
- [x] `P2` `bug` `@ai` Dead code from the "Strip the security verticals" commit is gone. One correction to the original note: the `osint` branch in `get_recommended_setup()` is a *prompt-keyword* branch, not an agent branch — "research"/"analysis"/"report" still match, so it was kept with the OSINT wording removed rather than deleted. Original note follows: the `icons`/`labels` dicts, `PROVIDER_MODEL_BOXES`-style mappings, and worker attributes (`osint_worker`, `osint_heavy_worker`, …) for the six deleted agents are still defined but unreachable, and `get_recommended_setup()` still has an `osint` keyword branch that can never fire since no `osint` agent exists. Also: the hidden `agent_box` combo still injects `"manager"` into its item list (`for extra in ("manager", "author"): ...`) even though `ManagerAgent` no longer exists. None of this is user-visible today, but it will confuse the next person who greps for those agents assuming they're live.
- [x] `P3` `infra` `@ai` `Imprint.spec` no longer lists `whois` and `dns`/`dns.resolver` as hidden imports "for `providers/domain_lookup`" — that module was deleted in the same strip commit. Harmless (just bundles two unused packages) but worth pruning next time the spec is touched.
- [x] `P2` `design` `@ai` FORK_PLAN.md step 4 — the left-nav sidebar is now mode tabs (Write / Audio / Web / Gigs / Creator) — is the one step of the fork plan not yet done; everything else in "Order of work" shipped. Needs a UX call on whether tabs are actually better than the current collapsible-category sidebar now that it's live and working.
- [x] `P3` `docs` `@ai` Added `docs/agents/course.md` — every other agent has a reference page under `docs/agents/` opened by its panel's Docs button; the Course Generator has no panel (it's CLI-only, §5.8) so it has no Docs button either, but a reference page would still help since `run_course.py --help` is the only current documentation of its flags.
- [x] `P0` `security` `@ai` Paid API calls bypassed every guardrail outside the chat panel — 22 sites constructed a `ChatWorker` directly. `authorize_request` / `record_request` / `abandon_request` / `note_request_usage` now wrap all 19 previously unguarded sites.
- [x] `P1` `bug` `@ai` Agent panels crushed when the window was narrow — 13 control rows converted to `FlowLayout`; splitter minimum 1460px → 985px
- [x] `P0` `bug` `@ai` No timeouts on any paid cloud client — `services/api_limits.py` (120s, 1 retry) now shared by all five
- [x] `P1` `bug` `@ai` Twelve silent `except: pass` blocks replaced with `_note_failure`, which writes to stderr and attaches the reason as a tooltip
- [x] `P1` `testing` `@ai` Test coverage was inverted — the money logic was the untested part. `test_cost_and_limits.py` (31 tests) and `test_request_guard.py` (30 tests), both mutation-verified.
- [x] `P2` `feature` `@ai` Saved Chats — agent filter above the search box, double-click to rename

- [x] `P1` `bug` `@ai` **Gemini billing restored.** Current 3.8/3.7/3.6/3.5 Flash, 3.1 Pro and 2.5 Flash/Pro paid-tier rates were checked against Google's published pricing. Stale zero rows and the old 2.5/15 provider reserve are corrected without overwriting different nonzero user edits. Zero legacy rows cannot shadow the conservative 4/18 unknown-model reserve. Cost/limit tests include Gemini. Recheck provider rates, especially the announced 2027 Flash changes and modality-specific pricing.

- [x] `P2` `docs` `@ai` **Learning Centre** — a seven-page searchable operating playbook (`docs/learn/`) covering setup, every control and agent, measured income experiments, automation playbooks, safe operation, weekly improvement, and troubleshooting. Its test suite checks pages, images, links, agent coverage, search, and the unit-economics standard for income guidance.

- [x] `P1` `security` `@ai` **Higgsfield renders bypass the request guard.** Fixed: the Creator flow asks Higgsfield's official estimate endpoint for the exact prepared request, converts that USD quote to the guard's EUR budget, then requires the normal external-API approval before generation. Successful renders are recorded against session and daily caps; failed, NSFW and canceled jobs are not charged. `creator` permits the `higgsfield` backend and the global API permissions row now has an explicit Higgsfield checkbox. Original note:  `creator_generate_video()` submits straight to the API: no `authorize_request`, no `record_request`, so a video render is invisible to the session and daily caps, to the spend counters and to the confirmation prompt. This is the same class of bug as the P0 above — paid calls made outside the one guarded path — reintroduced by the agent that added a second paid provider. Higgsfield bills per render, so this is real money, not a rounding error. Needs its own cost model too: the guard is priced in tokens and a render is not.
- [x] `P1` `docs` `@ai` The Learning Centre now covers the Creator agent and the audiobook Listen tab, and `scripts/make_learning_shots.py` has a shot of each. All nine screenshots were regenerated after the September 2026 GUI pass, so the guide shows the shell that ships.
- [x] `P1` `feature` `@ai` **OnlyFans venture intelligence.** Added a top-level OnlyFans business workspace for overview, ranked trends/opportunities, content intelligence, monetization and owned analytics, market/competitive density, and strategy. Selected opportunities hand structured evidence, freshness, risk, format, pricing hypothesis, and deliverables to the platform-agnostic Creator workspace. Live search, discussion, and adult-industry sources sit behind resilient adapters; until configured, the UI uses conspicuously labelled demonstration data and never presents directional scores as revenue forecasts or imported receipts as profit. Connector limitations and setup are documented in `docs/creator_trend_intelligence.md`.
- [x] `P1` `feature` `@ai` **Explainable BEST FIT recommendations.** Every visible provider/model pair is bound to one constraint-first engine. Each agent owns its requirement profile; the host filters modality, retirement, availability, API permission, budget, aspect and duration before scoring quality, reliability, cost, speed, context and privacy. Provider menus mark the best eligible provider overall and model menus recompute the best option inside the provider selected by the user. Dedicated UI roles carry reasons, scores and confidence, with contract tests preventing new selectors from being left unbound.
- [x] `P1` `design` `@ai` **Section hierarchy and OnlyFans decision UI.** Section titles now use readable normal-case semibold typography instead of field-label small caps. Audiobook conversion settings remain above the fold. OnlyFans uses a seven-column comparison table with stable headers, selected-signal evidence in detail, guided content/monetization/strategy cards, explicit measurement and stop rules, and a direct Creator handoff from the content plan.
- [ ] `P1` `design` `@ai` **Refactor Phase 4 — panel extraction.** Foundation shipped 2026-09-14: flat implementations moved to `agents/<key>/agent.py`; package public APIs replaced private-file imports; `agents/catalog.py` now owns roster/workspace/recommendation metadata; and every visible, CLI and internal agent owns README/TODO/SUGGESTIONS files. Music and Site Builder now own their panels and handlers; OnlyFans was already there. Audiobook now owns its Convert/Listen layout and listening actions, with paid conversion handlers still on the host. Remaining work is tracked per package: move the other panels and handlers out of `main.py`, then relocate services proven exclusive to one agent. See `docs/agent_project_structure.md`.
- [x] `P2` `feature` `@ai` Creator Earnings is a structured, evidence-labelled dashboard: statement and attributed totals stay separate, PPV price points have a chart, and asset, channel, hook and entered-cost ROI comparisons are visible without a text dump.
- [x] `P3` `feature` `@ai` Audiobook player has a sleep timer, embedded-chapter and saved-mark navigation, and space/arrow-key controls, with persistence and headless tests.
- [x] `P1` `design` `@ai` **GUI overhaul.** Header bar plus two fixed rails replacing the splitter; every panel rebuilt on `ui/forms.py` (section label + hairline instead of group boxes, labels above inputs on an equal-stretch grid, one filled button per page, Stop hidden until it can do something). One control height enforced in the stylesheet — QLineEdit / QComboBox / QPushButton / QSpinBox / QDateEdit came out at 48 / 46 / 48 / 53 / 53 from their natural size hints, and a control a few pixels taller than its neighbour drops its whole field below the row. 58 emoji removed from control labels and 36 colon captions folded into fields. Four new mutation-verified tests: shell overlap at every size, the creator compose grid packs contiguously, no emoji in a control label.
- [x] `P2` `feature` `@ai` **The image model is a control.** Updated for the provider's September 2026 catalog: DALL·E 2/3 were removed from the API, so the Gigs and Video workspaces offer GPT Image 2.5 Sunburst, GPT Image 2.5 Flare and GPT Image 2. Every selectable model has a real request path and retired IDs are rejected before a paid call.
- [x] `P1` `bug` `@ai` **Per-unit billing.** Fixed: `log_request(flat_cost_eur=)` skips the token arithmetic, `authorize_request(flat_cost_eur=)` hands the validator the real price, rates live in `config/pricing.json` under `per_unit_usd` where **zero means unknown, not free**. Gigs images, Higgsfield renders, audiobook TTS and video renders all count against the caps now. Original note:  The budget guard is denominated in tokens, so it cannot express "one image", "one render" or "one thousand characters". Three paid paths are therefore invisible to the session and daily caps: Gigs logo generation, Higgsfield video, and TTS. The Gigs panel now shows a per-image estimate next to the button, but it is display only. Same root cause as the Higgsfield item above; fixing one should fix both.
- [x] `P1` `feature` `@ai` **Video mode.** `vidforge` runs in-process as an eighth agent, imported from the nested repo rather than vendored — see `docs/agents/video.md` for why. Long-form and social clips are the same `produce()` call with config overrides. `Imprint.spec` ships the package plus its config and assets; `main.py --selftest` proves it in a frozen bundle.
- [x] `P1` `feature` `@ai` **Video provider/model routes.** The Video workspace offers current GPT Image models; Gemini Omni 1.1 and all Veo 3.1 tiers; Qwen/Wan 3.0, Prime and 2.7; Higgsfield Seedance; Pexels; and local gradient visuals. Sora 2/2 Pro were retired from the new-job menu ahead of their September 2026 API shutdown, with the legacy adapter retained for old jobs. Scene models flow through vidforge; supported direct models create/poll/download and join the same library. Duration/aspect controls follow each API, every paid request uses a per-second reserve or provider quote, and create calls cannot silently retry into duplicate jobs. DALL·E is absent because its APIs were removed; DeepSeek, Anthropic, Kimi and Ollama are not visual providers because they expose no video-output API.
- [x] `P1` `feature` `@ai` **Social mode.** Campaigns, per-platform drafting, cadence scheduling, and direct posting for YouTube / Reddit / Pinterest. The other five platforms are drafting-only and the Accounts tab says exactly why. Nothing posts unattended.
- [x] `P1` `security` `@ai` **The audiobook conversion never called `authorize_request`.** A book is often the most expensive single action in the app and it went out behind a hand-rolled Yes/No box — no budget check, no spend counter, nothing against the daily cap. Its estimate was `min(25, max(0.5, megabytes * 0.80))`, a number with no relationship to what OpenAI charges, while `services/narrator/converter.py` had carried `load_text`/`count_text_tokens`/`estimate_costs_usd` all along. Now priced from the real extracted text and guarded. That is the last of the unguarded paid paths.
- [x] `P2` `bug` `@ai` **`_seed_default_agents` could not add a provider to an existing agent.** INSERT OR IGNORE only ever helps a *missing* agent, so an existing row kept its original `allowed_providers` forever and adding a backend silently did nothing on every machine that had run the app before. `_reconcile_agent_providers` merges new providers in, additively.
- [x] `P2` `testing` `@ai` **Tests were writing to the live spend database.** The `tracker` fixture was a bare `UsageTracker()`; the read-only helpers never noticed, and the first test to call `log_request` put nine fabricated requests and €0.47 into the real counters. Isolated to a temp database seeded from `pricing.json`, and the fabricated rows removed.
- [x] `P1` `research` `@ai` **Identified: a peer Claude Code session, pushing on instruction.** Not a hook, not a daemon. Four Claude Code sessions were running concurrently; the one working on `git_autosync` pushed imprint's backlog when asked to, and also committed `84c179e` into this repo while this file was being written — which is how it was caught.

  **The "every commit" premise was wrong, and it was mine.** Measured: `git reflog show origin/main` has **6 entries against 67 commits on main**, with commit→push gaps of **8s, 36s, 2h56m, 31m, 1s and 47h**. That is occasional manual pushing. The original claim generalised from the two most recent pushes, which happened to land seconds after two of my own commits — a biased sample of two, stated as a pattern going back to August. (An earlier note here said 5 pushes against ~57 commits; both figures were slightly low.)

  Ruled out by inspection, each of which was worth checking: `core.hooksPath` is unset globally and locally, `.git/hooks/` is empty, there is no crontab, no `fswatch`/`watchman`/`gitwatch` process, no Claude Code hook in any `settings.json`, and no GUI git client running. The `com.netrunner3000.git-autosync` LaunchAgent fires at **03:30 only** — no `WatchPaths`, no `StartInterval` — and its own log for 2026-09-09 shows it *skipping* this repo.

  **What is verified vs. reported.** Independently checked: nothing sensitive is tracked — `.env` is git-ignored, only `.env.example` is committed, and there are no keys, `.pem`, `id_rsa` or `.secrets` files in the tree. The claim that each push was preceded by a full-history `gitleaks detect` comes from the peer session's own report; a manual gitleaks run leaves nothing in the autosync logs, so it could not be confirmed from here.

  imprint stays out of `autosync_repos.txt` on purpose: autosync pushes only the *checked-out* branch, so it would publish whatever feature branch was current under a timestamp commit message.
- [x] `P1` `infra` `@ai` **Fixed: 7 of git_autosync's 12 configured repos were silently skipped.** The *effective* config — `~/Library/Application Support/git_autosync/autosync_repos.txt`, not the copy in the repo — still held pre-reorg bare names, so `convert_epub`, `image_tools`, `sentinel_ai`, `vpn_agent`, `unblock_tracker`, `create_and_publish` and `vidforge` resolved to nothing and were logged as `SKIP (not a git repo)` while the nightly run reported success. Several projects had no automated off-machine push for the period between the reorg and the fix. It now lists 21 entries with correct subpaths (`toolbox/…`, `sentinel_fork/agents/…`, `imprint/vidforge`). Fixed by the git_autosync session, not here.

- [x] `P2` `infra` `@ai` **Resolved: autosync gained a `push-only` mode.** Sweeping imprint nightly produced three `autosync: <timestamp>` commits (09-10, -11, -12), one burying most of a Learning Centre rewrite under a message describing none of it. `git_autosync` now takes a per-repo flag: push commits that already exist, never stage or commit the working tree, never publish a branch with no upstream. `imprint` and `imprint/vidforge` are set to it in the live config, verified by dry run — it pushes the real commits and leaves the in-progress tree alone. The gitleaks history scan still runs; only the staged scan is skipped, because nothing is staged.
- [x] `P2` `infra` `@ai` **Committed a finished combo box rework that had been left in the working tree.** Written by another Claude Code session on 2026-09-14 and orphaned when it ended: SVG chevron replacing Qt's native arrow, popup styling, a `CompactCombo` variant, popup scroll behaviour, four new layout tests and regenerated screenshots. Green (502 tests) and coherent, so leaving it uncommitted protected nobody — and with `push-only` now set on this repo, the nightly sweep no longer picks up a dirty tree either, so uncommitted genuinely means unprotected. `AGENTS.md` gained the convention: commit before going idle, and committing another session's finished work is preserving it, not cleaning it away.
- [x] `P2` `bug` `@ai` **The app shipped Sentinel's logo.** `assets/icon.icns` and `assets/icon_source.png` were byte-identical to `sentinel_fork`'s — a surveillance eye in a shield, inherited at the fork. Imprint's own artwork sat beside them as `icon-v2.icns`, referenced only by `Imprint.spec`, so a frozen build showed the book and a live-launcher install showed the eye: the same app with two logos depending on which script ran last. The `-v2` naming *was* the bug — the obvious filename held the wrong image, so `install_app.sh` was wrong by default. Canonical names now hold the Imprint artwork and the suffixed copies are gone. **The installed bundle still shows the old one until `scripts/install_app.sh` is re-run.**
- [x] `P2` `docs` `@ai` **README chapter 18, "Installing and Packaging".** There was none, which is how two install paths diverged unnoticed. Documents that `install_app.sh` (live launcher, everyday) and `build_app.sh` (frozen, for another machine) both write to `/Applications/Imprint.app` so the last one run wins, how to tell which you have (`applet` vs `Imprint` in `Contents/MacOS/`), that the icon is copied at install time so changing it needs a reinstall, and what `--selftest` covers.
- [x] `P1` `bug` `@ai` **vidforge was shadowing Imprint's own `main`.** `video.studio._load()` put `imprint/vidforge/` at the *front* of `sys.path`, and that directory is a whole application — vidforge's `main.py` and `app.py` sit beside the package — so once the Video mode loaded, `import main` resolved to vidforge's. The running app hid it entirely (`main` is in `sys.modules` long before Video is touched); it surfaced as 132 collection errors the first time a test imported the bridge at module scope, none of which reproduced running the files one at a time. Appending keeps Imprint's root ahead.
- [x] `P2` `testing` `@ai` **The vidforge boundary is enforced now.** `tests/test_vidforge_contract.py` pins `produce()`'s signature, `Reporter`'s hooks, the eight stage keys and their weights summing to 1, and the config keys `clip_overrides()` writes. vidforge is a separate repo, so each of those is a reasonable change there that silently breaks the Video tab here — a vertical clip rendering landscape still costs a full render. Skips when vidforge is absent. Mutation-verified.
- [x] `P1` `feature` `@ai` **Creator platform-policy profile.** Every destination can hold a dated, source-backed record of synthetic-persona permission, verified-depicted-owner rule, AI disclosure, and publishing method. Unknown policy blocks synthetic-persona generation; the Creator still drafts for human/manual publication only. The separate `@me` verification of actual OnlyFans rules remains open.
- [x] `P2` `feature` `@ai` **Creator ROI loop.** Calendar assets now retain campaign/channel and measured draft cost in EUR; the user records actual publication, link, reach, clicks, subscriptions, PPV purchases, attributed revenue and all-in USD cost with source/window. Earnings compares assets, hooks, channels and PPV prices; ROI is shown only on entered same-currency cost, and statement receipts are never double-counted.
- [x] `P3` `feature` `@ai` Social Analytics stores the posted item's angle plus manually entered reach, clicks, report source and window; the new tab shows per-post click-through without treating it as sales or a fair cross-audience comparison.
- [x] `P2` `design` `@ai` ~~Two rows of navigation both said "Publish".~~ Renamed: the workspace is `Author` (was `Write`) and its stage tabs are `Book Author` / `Publishing Manager` (was `Draft` / `Publish`) — `agents/catalog.py`'s `AgentSpec.label`/`.workspace` fields, reflected in the header bar's `agent_titles`/`agent_subtitles`. The author panel's own inner mode toggle is unchanged (`Write | Publish & Market`), but it no longer collides with a workspace of the same name.
- [x] `P3` `bug` `@ai` Studio Assistant now has its own workspace tab; registry seeding no longer deletes it, and the Learning Centre has an operating lesson for the shared chat panel.
- [x] `P2` `docs` `@ai` **Documentation centre.** `ui/docs_center.py` — a searchable technical reference browser opened from the header **Docs** button (active-agent page) and the right rail's general **Docs** button (shared-system overview), both reading `docs/agents/manifest.json` for grouped contents, heading-level search, an on-page outline and previous/next navigation. `docs/agents/overview.md` defines the boundary against the task-first Learning Centre so the two stop duplicating each other.
- [x] `P2` `feature` `@ai` **Learning Centre v2 / Income Lab.** Replaced the five-page guide with a 27-lesson manifest-driven academy (`docs/learn/manifest.json`, `docs/learn/modules/`) built around an evidence-gated income methodology: label the evidence, define one measurable offer, pre-register a fair experiment, calculate unit economics, keep funnel/attribution definitions honest, choose stop/repair/repeat/scale under uncertainty, then automate only after the promotion gates pass. The worksheets do deterministic arithmetic on user-supplied or explicitly hypothetical numbers and never fetch market data or project earnings. Chapter 21 ("Earning Income") was rewritten around this method; the old forecast-style figures are kept out of the rendered doc (commented out) rather than deleted.
- [x] `P2` `design` `@ai` **Structured status cards.** `ui/status_cards.py` replaces the collapsed SYSTEM/ROUTING/API KEYS panels' paragraph-of-text style with scannable rows and state badges: Resource Monitor keeps its colour-coded thresholds (tightened for CPU/RAM/Swap), Routing separates **Last decision** from the **Best fit** recommendation (score, confidence, reason, setup readiness), and API keys shows **Configured** / **Not configured** / **Check failed** per provider without ever displaying secret values.
- [x] `P2` `feature` `@ai` **Suno-assisted Songs & Albums.** New Music tab (`agents/music/suno_panel.py`, workflow doc `agents/music/SUNO_WORKFLOW.md`): draft lyrics and Suno-ready style prompts from a title/track-count/brief, edit and copy them into the user's own Suno account (no API key, no auto-generation, Suno's own costs untracked), then import the downloaded audio into `data/music_library` with saved track order and album metadata. `agents/music/agent.py`'s Income Roadmap section was also rewritten to stop quoting a universal per-stream rate and instead require a sourced, dated, user-supplied payout scenario labelled hypothetical.
- [x] `P2` `feature` `@ai` **OnlyFans → Creator direct teaser handoff.** The OnlyFans dashboard's Content Intelligence tab gained a third action, **Generate SFW Teaser** (`teaser_requested` signal), alongside the existing campaign-brief handoff — it routes the selected opportunity straight into Creator's Higgsfield pipeline to produce a real safe-for-work promotional clip rather than only a drafted brief.

**Re-analysis 2026-09-20** — eight-subsystem review; every high-severity claim below
was independently re-verified against the code before filing.

- [x] `P0` `security` `@ai` **ElevenLabs shorts are unguarded.** Fixed same day: `_authorize_short_narration()` wraps all three launch sites (only the ElevenLabs branch — the default narrator is the free on-device voice), keeps the returned token rather than resolving by the shared "manuscript" name, and records/abandons in every done/error handler. `elevenlabs_tts_per_1k_chars` added to pricing.json shipping as 0 = unknown → the paid voice refuses until a real rate is filled in; an ElevenLabs checkbox joined the API permissions row, and `elevenlabs` joined manuscript's registry providers with `_reconcile_agent_providers()` carrying it onto existing installs (verified against a migrated DB). Original: `manuscript_generate_short` (main.py:6856), `quote_finder_generate_short` (7016) and `calendar_generate_asset` (7167) launched `ShortsWorker` with no guard and pricing.json had no ElevenLabs key.
- [ ] `P1` `bug` `@ai` **Streaming discards real provider usage.** `run_backend` prefers `stream_chat` for every cloud backend and all six wrappers yield text only, so cloud chat is billed on the chars/4 estimate and the Kimi cached-token billing (a DONE item above) never actually fires (main.py:8502). Capture the final-chunk usage each provider sends and pass it through `ChatWorker`.
- [ ] `P1` `bug` `@ai` **Finish the guard-token migration.** Most flows discard the token `authorize_request` returns and record/abandon by agent name; concurrent flows sharing a key ("video" = Video tab + Social clips, "creator" = drafting + teaser, "manuscript" ×3, "author" ×3) FIFO-pop the wrong pending context — a completed paid render can bill €0.00 (main.py:3126, 3969). Keep the token per flow; never abandon by bare name when the flow's token is None. Do it site-by-site during the Phase 4 panel moves.
- [ ] `P1` `bug` `@ai` **In-flight authorized spend is invisible to the caps** — two concurrent authorizations can each consume the full remaining budget; nothing reserves the estimate between authorize and record (main.py:8358). Stash the computed estimate on the pending request and count open reservations in the validator inputs.
- [ ] `P1` `bug` `@ai` **Worker-lifecycle sweep.** `QThread.terminate()` at three sites (stop chat main.py:8660, creator stop 4615 — no `cancel()` at all, `closeEvent` 9299); replacing a still-running Author worker aborts with `QThread: Destroyed while thread is still running` (5780); `closeEvent` ignores every worker except chat, losing the paid record for an in-flight render. One idiom everywhere: cancel + disconnect + `deleteLater` on `finished`, and refuse to restart while running.
- [x] `P1` `bug` `@ai` `agent:social` **YouTube publisher calls a signature that does not exist.** Fixed same day: the publisher now builds the Config through `video_studio.load_config()` (which keeps vidforge's two-key public-publish guard enforced) and calls the real `upload(cfg, video, meta_dict)`, reading `result["video_id"]`. Original: `services/social_publishing.py:188` passed `(path, title=, description=, privacy=)` and TypeErrored on every upload.
- [x] `P1` `bug` `@ai` `agent:social` **Social Stop calls nonexistent `ChatWorker.stop()`** (main.py:3009) — fixed same day: `cancel()`. Clearing `social_worker` on finish (a stale Stop press after completion hits the same shape) folds into the worker-lifecycle sweep above.
- [x] `P1` `bug` `@ai` `agent:fiverr` **Unknown per-image rate is coerced to free.** Fixed same day: an unpriced model now refuses with a "No Price Configured" warning before `authorize_request`, mirroring the audiobook posture. Original: `flat_cost_eur=image_cost if image_cost is not None else 0.0` (main.py:5370) converted "no rate configured" into €0.00 — and passing None through would have been no better (falls back to chat-cost-estimating the prompt).
- [x] `P2` `bug` `@ai` **Client hardening pass.** All six fixed same day: Qwen chat client now pins `timeout`/`max_retries` from api_limits (it landed five days before api_limits and never got wired); the four OpenAI-compatible stream loops skip empty-`choices` chunks instead of crashing; Anthropic `chat()` joins the text blocks instead of indexing `[0]` (empty content no longer raises, multi-block responses no longer truncate); the image-URL `urlopen` fallback got the shared timeout; `UsageTracker` gained a `CLOUD_BACKENDS` set covering anthropic/kimi/qwen/higgsfield; `resolve_backend_model`'s `allowed_apis` includes `"qwen"` — which also closes the worse half where Hybrid mode sent paid Qwen requests with the checkbox unticked.
- [x] `P2` `testing` `@ai` **Money-test gaps, structural half.** Fixed same day: the four dead per-unit tests are collected again (a column-0 `per_unit_eur_per_usd` helper inserted mid-class had de-indented them into unreachable statements; moved above the class — suite went 699 → 703, all green), and conftest.py now redirects `database.DB_PATH` to a temp database and runs `init_db()` before any test module imports main, making isolation the default instead of a per-fixture convention (`test_creator_v2` had been INSERTing into the live dev data/imprint.db; the change also exposed and covered `test_creator_trends` leaning on the dev schema). A selection-signal test for the audiobook panel landed with the panel fix.
- [ ] `P2` `testing` `@ai` **Money-test gaps, behavioural half.** No test exercises `flat_cost_eur` through `authorize_request` or budget blocking end to end (deleting the `if flat_cost_eur is not None` branch at main.py survives the suite); audiobook billing is decided by string-matching an emoji banner in stdout, untested (main.py:7947) — replace the sniff with an explicit exit-code/marker protocol from the converter subprocess, then pin it.
- [ ] `P2` `design` `@me` **Per-agent cap: per-request, not per-day.** Validator gate 7 compares one request's estimate against the whole agent budget, so a €1.00/day agent can spend €0.99 repeatedly, while the refusal message claims €X/day (services/validator.py:91). Decide: track per-agent daily spend, or reword the cap.
- [ ] `P2` `design` `@ai` **Dead code sweep.** `services/model_router.py` (170 lines; "Auto Route" just echoes the current selection — main.py:8092 never calls it), the float-money `check_budget_before_request` (main.py:670), the three redundant Sora gates once the API closes 2026-09-24 (`sora_is_retired` already has no production caller; also drop the catalog rows, `OPENAI_VIDEO_MODELS`, `sora_cost_usd`), and the dead worker classes codified in the AgentHost protocol (ui/workers.py:270).
- [ ] `P2` `bug` `@ai` `agent:creator` **`save_persona()` wipes omitted fields** — every save erases `reference_images`, which has no writer at all (services/creator_profile.py:119). Merge instead of replace, or add the missing writer.
- [ ] `P3` `bug` `@ai` **Data-layer smalls.** `init_db` first-run check is file-existence, so a pre-init placeholder DB suppresses the JSON-history migration forever (services/database.py:461); `content_calendar.build_calendar` bunches multi-week cadences into consecutive days (content_calendar.py:46); `audiobook_library.scan()` crashes the listing if a file vanishes mid-scan (audiobook_library.py:129); `_migrate_usage_log` aborts the whole migration on one malformed row, unlike `_migrate_runs` (database.py:1050).

## v3 — later

- [ ] `P2` `feature` `@ai` Local model provider (Ollama) as a zero-cost fallback when the budget cap is hit
- [ ] `P3` `infra` `@ai` One shared retry-with-backoff wrapper across providers, replacing per-client handling
- [ ] `P3` `feature` `@ai` Export a run — prompt, response, usage, cost — as a single markdown file

---

## Shipped since the last review

- **Documentation centre + Learning Centre v2 / Income Lab** — a searchable technical reference browser (`ui/docs_center.py`) alongside a rebuilt 27-lesson academy built around an evidence-gated income methodology instead of forecast-style earnings guidance; structured System/Routing/API-key status cards (`ui/status_cards.py`) replaced paragraph-of-text diagnostics.
- **Suno-assisted Songs & Albums** in the Music agent, plus an OnlyFans → Creator direct **Generate SFW Teaser** handoff that requests a real clip instead of only a campaign brief.
- **Renamed to Imprint**, with migrations that carry the Application Support directory and the database file across the rename — the `.env` holding the API keys lives in that directory, so a rename without them looks exactly like the app losing everything.
- **Creator agent** — subscription account planning and drafting, voice profiles, persona bibles, media library, Higgsfield promo video, revenue attribution, agency view, performer records. No posting path: OnlyFans has no usable API and the automation their terms allow is the kind that assists rather than replaces.
- **Audiobook library and player** with resume, closing the gap where the app could produce an audiobook and then not play it.
- **Right rail** cut from six always-open cards to two plus three collapsibles; `COST` and `BUDGET` were showing the same two numbers twice.
- **Layout collapse fixed** — controls no longer draw on top of each other or clip off the right edge at any window size, pinned by `tests/test_panel_layout.py`.

---

# Detail

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

**Status: DONE (2026-08-12).** `authorize_request` / `record_request` /
`abandon_request` / `note_request_usage` live on `GodAI`, and all 19 previously
unguarded `ChatWorker` sites call them — 20 `authorize_request`, 19
`record_request`, 17 `abandon_request`. Verified: all 12 agent panels are
refused when the provider checkbox is off, and a completed run now bills the
session and writes a Saved Chat under its own agent name.

Two things surfaced while wiring it:

- `Registry` reads the **SQLite DB**, not `config/registry.json` (the JSON is
  only a seed via `_migrate_registry`). Both were updated.
- `chat`, `osint` and `manuscript` did not list `anthropic` or `kimi` in
  `allowed_providers`, and no tool listed them either — so picking Anthropic or
  Kimi anywhere was already being rejected as "does not permit provider" before
  any of this. Fixed in the DB and the seed.

Not wired, deliberately: `roi`, `investment` (moved to the SONAR app — see the
comment in `_seed_default_agents`) and `ops_identity`, none of which have an
agent module or panel here. **`ops_identity` is still listed in the sidebar and
`agent_titles` despite having no implementation — a dead menu entry worth
removing.**

Concurrency caveat: `_pending_requests` is keyed by agent name, so two
simultaneous runs of the *same* agent would overwrite each other's context. The
panels disable their run button while a request is in flight, so this is not
reachable today — but keyed-by-run-id would be more robust.

## 2. `main.py` is too big — IN PROGRESS (11,902 → ~10,400 lines)

One file holds 17 agent UIs, routing, cost logic, history and styling. The cost
is concrete: a checkbox-spacing fix had to go in the global stylesheet because
the pattern repeats everywhere, and a card-padding fix touched 6 identical
`setContentsMargins` calls. (`list_models()` ×64, `QGroupBox(` ×57,
`setContentsMargins` ×75, `provider_box.addItems` ×13.)

**Fix:** one module per agent panel (`ui/panels/osint.py`, …) plus a shared
`AgentPanel` base for the provider/model/actions row all 17 rebuild by hand.
Do this *after* #1 — the shared helper makes the seam obvious.

**Plan written: `docs/refactor_plan.md`** (2026-08-12). Measured layout, a
five-phase order that ends green at every step, and the finding that makes it
tractable: each agent vertical is ~75% self-contained and the code it reaches
outside itself is the same ~15-member interface every time (provider clients,
the request guard from #1, `run_backend`, `agent_instances`, `_note_failure`).
**Phase 1 is DONE (2026-08-12):** `ui/workers.py` (212), `ui/widgets.py` (161),
`ui/style.py` (315) and `ui/tooltips.py` (252) extracted verbatim; `main.py`
11,902 → 11,007. Verified at runtime, not just by import — the stylesheet is
applied and tooltips are live.

**Phase 2 is DONE (2026-08-12):** the four `show_*` dialogs moved to
`ui/dialogs.py` (735 lines), a net −696 in `main.py`. `GodAI` keeps four
three-line wrappers, so no call site changed. Each body is byte-identical to the
original after `self`→`app` and one dedent — diff-verified rather than eyeballed.

The trap worth carrying into Phase 3: **a missing import does not fail at import
time.** The moved bodies referenced five provider wrappers plus `Registry` and
`Validator`; `ui/dialogs.py` compiled and imported fine, and only
`show_model_guide` raised `NameError` when actually opened. Guessing the import
list from a regex missed all seven; walking the AST for `Load`ed names not bound
in the module found them at once. The check that caught it was stubbing
`QDialog.exec` and opening all four dialogs, asserting on their contents.

**Next: Phase 3** — the `AgentHost` protocol and `AgentPanel` base. This is the
first phase with a design decision in it: composition over mixins.

## 3. Other agent panels still crush when the window is narrow

`FlowLayout` (main.py) fixed the chat panel: a `QHBoxLayout` reports the sum of
its children as its minimum width, so a long control row pins an impossible
minimum on the pane and Qt compresses buttons past their own minimums —
labels get chopped to "uto Rout", "ecomme".

**Status: DONE (2026-08-12).** 13 control rows converted to `FlowLayout`:

| panel           | min width before | after |
|-----------------|-----------------:|------:|
| AuthorPanel     | 1091 | 403 |
| WiFiPanel       |  803 | 462 |
| NFLBetPanel     |  728 | 473 |
| OSINTPanel      |  728 | 257 |
| OSINTHeavyPanel |  728 | 503 |
| WebdesignPanel  |  728 | 507 |
| ManuscriptPanel |  711 | 670 |
| BugBountyPanel  |  704 | 573 |

The result that matters: the splitter's minimum width is now **985px, under the
window's own 1000px minimum**, so the three panes fit at the narrowest allowed
window and nothing can be crushed. It was 1460px when this started.

Notes for future conversions:

- Rows come in three shapes and all three needed handling: `addLayout(row)`,
  `addLayout(row, r, c, rs, cs)` into a `QGridLayout`, and `QHBoxLayout(widget)`
  built straight onto a container.
- `FlowLayout.addWidget` now accepts (and ignores) `QBoxLayout`'s stretch and
  alignment arguments, so a `QHBoxLayout` can be swapped in without touching
  call sites — the fiverr panel passes a stretch factor.
- `addStretch()` calls were dropped: a stretch has no meaning once items wrap.

Not converted: the API-key rows (771px). They live inside a scroll area, so
their width no longer drives any pane minimum.

## 4. No timeouts on any cloud client

`ollama_client` sets 10s/300s. All five paid clients — `openai_client`,
`deepseek_client`, `kimi_client`, `gemini_client`, `anthropic_client` — passed
no timeout at all, so a hung connection froze that agent with no recovery.

**Status: DONE (2026-08-12).** `services/api_limits.py` holds the shared values
(120s, 1 retry) and all five clients use them. Verified on the constructed SDK
objects, not just in source; a request to a black-hole address now raises
`APITimeoutError` instead of hanging.

Two notes for whoever tunes this: google-genai's `HttpOptions` takes
**milliseconds** while the other four SDKs take seconds, and the timeout applies
*between streamed chunks* rather than to the whole generation — so 120s does not
cap a slow model.

## 5. Silent `except: pass` blocks

Failures vanished, including around history loading and model listing — if
`load_history_list` threw, the list was silently empty and looked identical to
"you have no saved chats".

**Status: DONE (2026-08-12).** All 12 were replaced with
`except Exception as exc: self._note_failure(...)`. The helper writes
`[warn] <context>: <type>: <message>` to stderr — which the app launcher already
captures in `/tmp/sentinelai_launch.log` — and, where a widget is passed,
attaches the reason to it as a tooltip so an empty model dropdown explains
itself without reading a log.

Covered: the eight `*_load_models` methods, `apply_agent_recommendation`,
`_ops_write_env_key`, `load_history_list` and `closeEvent`. The last two are
still non-fatal on purpose (shutdown, and a key that is already saved in the
database) — they just say so now instead of disappearing.

Verified by injecting a `ConnectionError` into a provider: the failure reaches
stderr and the tooltip, the call does not raise, and the UI survives.

One `except Exception: pass` remains on purpose, inside `_note_failure` itself:
the error reporter must never raise.

`RunLogger` was not used for this — its API is run-scoped (`start`/`finish`/
`cancel`) with no general note method. Adding one would be the tidier home for
these if they ever need to be queryable.

## 6. Test coverage is inverted

The scenario tests cover agent prompt construction, but nothing covered
routing, cost estimation, validation or history — the money logic was the
untested part.

**Status: DONE (2026-08-12).** `tests/test_cost_and_limits.py` adds 31 tests
over the two things that decide whether money is spent and how much:
`Validator` (all ten rules, incl. per-agent/session/daily caps, the paid-provider
checkboxes, and ollama's exemption) and `UsageTracker` token/cost accounting
(each SDK's token naming, exact/estimated/mixed, cost invariants).

They are real tests, not decoration — verified by mutation: deleting the
session-budget check fails `test_request_over_session_budget_is_refused`, and
making the token estimate return zero fails three tests. Both mutations were
reverted and the sources confirmed byte-identical.

Design notes: `Validator` takes its registry by injection, so the gate tests use
a stub and never touch the database. `calculate_cost_eur` does read the pricing
table, so it is asserted on invariants (local is free, unknown backend is free,
cost rises with tokens, never negative) rather than hardcoded prices, which
would break whenever pricing is edited.

`authorize_request` / `record_request` / `abandon_request` are now covered too
— `tests/test_request_guard.py`, 30 tests. It builds `GodAI` once per module
(constructing it costs ~10s, so per-test was 118s and unusable) and swaps the
usage tracker, chat history and run logger for fakes, so no test bills a request
or writes into `data/chats/` — verified by comparing row and file counts either
side of a run.

What it pins is the behaviour where a bug costs money: a blocked or declined
request opens no run, recording without authorising bills nothing, double-record
bills once, and an abandoned request stays unbilled even if a late response
arrives. Mutation-verified — making `record_request` or `abandon_request` leak
their pending context fails the double-billing tests.

Deliberately not duplicated: the ten `Validator` gates and the token/cost maths
stay owned by `test_cost_and_limits.py`. `test_request_guard.py` keeps only three
edge cases that file does not reach, one of which pins a float-precision quirk —
`1.00 - 0.90 == 0.09999999999999998`, so a request estimated at exactly the
remaining budget is refused. It fails safe, and a switch to `Decimal` should
flip it.

---

## Smaller items

- Saved Chats: **DONE (2026-08-12)** — agent filter above the search box, and
  double-click to rename. The filter is built from the chats that exist, so it
  only offers agents actually used, and it intersects with the search box rather
  than overriding it. Rename writes the `title` field that
  `chat_title_from_data` already preferred but nothing ever wrote. One pass over
  the files serves both the filter options and the rows, so no extra disk reads.

  **Chat Projects Stage 2** is now implemented — see `docs/projects_roadmap.md`. Stage
  1 made the list tidier; Stage 2 turns a group of chats into a context
  bundle (instructions, defaults, optional budget), which is the part that
  earns its keep. The shared agent guard and Studio Assistant chat path both
  capture project context before dispatch, so an in-flight run keeps its
  original project even if the selector changes.
- Kimi prompt caching ($0.19/1M on cache hits, ~80% off input) is not modelled
  in `config/pricing.json`, so estimates for repeated context are conservative.
- `BUDGET` card: `Session €` / `Daily €` could share one row (~34px saved), but
  the two label+field pairs do not fit the sidebar's ~250px inner width without
  shortening the labels.
