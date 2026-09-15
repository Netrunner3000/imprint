# Learning Centre 2.0 — audited expansion plan

Status: **planning complete; implementation not started**  
Prepared: 2026-09-15

## Product goal

Turn the Learning Centre from a searchable handbook into Imprint's practical
operating academy: a place where a person can identify a goal, learn the exact
controls involved, complete a small verified result, understand the output,
measure its economics, and automate only the parts that have earned it.

The centre must explain every meaningful user-facing control and state without
becoming one enormous manual. It must also teach honest income experimentation,
not income promises. The success measure is not pages written; it is whether a
new user can complete a workflow and make the next evidence-based decision
without guessing what the interface or output means.

## Audit baseline

The current version has seven flat chapters, about 8,700 words, thirteen
reproducible screenshots, complete top-level agent coverage, sound unit-
economics principles, and useful troubleshooting. Its architecture is still a
chapter list plus a document reader.

The highest-impact problems are:

1. Search filters whole chapters. It does not return matching headings,
   excerpts, highlighted terms, or anchored results.
2. The 2,100-word Controls & Agents chapter contains ten agents and 138 table
   rows. Users still have to hunt after searching.
3. The app does not open help for the current workspace, tab, control, or error.
4. The fixed navigation, header, tables, and full-window screenshots make the
   minimum-size experience crowded and create competing scroll areas.
5. The content describes controls that are hidden or have changed. In
   particular, it teaches the old Studio Assistant `Use Recommended` flow
   instead of the visible `BEST FIT` / `BEST AVAILABLE` provider and model
   recommendations. Settings/key guidance and several OnlyFans labels have
   also drifted.
6. Important Creator, Publish, Social, Video, Audiobook, and OnlyFans states are
   summarized rather than taught.
7. Tests prove that documents exist, but not that a person can find or complete
   a lesson or that all visible controls are accurately covered.
8. The README still describes a five-page Learning Centre while the app ships
   seven pages, demonstrating that duplicated documentation already drifts.

## Experience model

The home screen will offer three ways into the same canonical curriculum:

- **Learn by goal:** create a first asset, validate an income idea, deliver
  client work, build a catalogue, build a content funnel, operate a creator
  venture, automate a proven workflow, or fix a problem.
- **Learn a workspace:** browse the ten visible agents, then the meaningful
  tabs and operations within each.
- **Find a control or error:** search by the label on screen or an error phrase
  and jump to the exact anchored explanation.

The centre will remember the last lesson and tutorial checklist state locally.
Reference pages will not pretend to have linear course progress. Guided paths
will show prerequisites, estimated time, completed steps, and the next useful
lesson.

## Information architecture

Target: **26 focused modules**, with room to split a module when it exceeds a
comfortable single-task lesson. The manifest, rather than filename order, owns
the navigation.

### 1. Home and guided paths

1. Learning Centre home and readiness check
2. Fifteen-minute first verified result
3. Choose a path: client service, catalogue, content funnel, or creator venture

### 2. Foundations

4. Navigate Imprint: workspaces, agents, tabs, status, and the right rail
5. Projects and persistence: what auto-saves, what must be saved, exports, and removal
6. Providers and models: BEST FIT, BEST AVAILABLE, confidence, overrides, and unavailable routes
7. Access and privacy: keys, permissions, local/cloud behavior, and data sent
8. Costs and limits: estimates, reservations, caps, Cost History, and unpriced work
9. Files and recovery: live launcher versus frozen app, storage, logs, backup, and restore

### 3. Agent Academy

One standardised module for each visible agent:

10. Draft
11. Publish
12. Audiobooks
13. Music
14. Video
15. Social
16. Site Builder
17. Client Gigs
18. Creator
19. OnlyFans

Each agent module contains:

- outcome, prerequisites, and when to use or avoid the agent;
- annotated screen and every meaningful control/state;
- a small worked input and numbered walkthrough;
- what each output means, what it does not prove, and how to judge it;
- objective acceptance checklist and a clear “done when” condition;
- expected cost category, cancellation behavior, privacy/rights gates;
- handoffs to other agents, common failures, and next action.

Creator, OnlyFans, Publish, Social, Video, and Draft receive the first detailed
passes because they currently have the largest gap between UI depth and guide
depth. Music also receives an early correction because its current prompt asks
for “realistic monthly projections,” which conflicts with the evidence standard.

### 4. Income Lab

20. Evidence before production and the evidence passport
21. Define one measurable offer and qualified opportunity
22. Design a fair bounded experiment
23. Unit economics and owner-time economics
24. Funnels, attribution, cohorts, currency, and comparable periods
25. Uncertainty and the stop / repair / repeat / scale decision
26. Automation maturity and weekly portfolio review

End-to-end playbooks—productised service, book/catalogue, content-to-offer,
creator subscription, music release, and website lead funnel—will be guided
paths composed from these canonical lessons rather than copies of the same
rules. Quality, safety, troubleshooting, metric definitions, templates, and
advanced/CLI material remain searchable reference collections.

## Lesson and visual design

The permanent hero is replaced by a compact title/breadcrumb bar after the
home screen. Wide layouts use grouped navigation, a capped 65–85-character
reading column, and an in-page outline. At narrow widths the navigation becomes
a drawer so the article has one primary vertical scroll.

Reusable blocks will make instructions scannable:

- Outcome and prerequisites
- Do this now
- Why it matters
- Input → action → output
- How to read the result
- Decision rule
- Evidence level
- Cost or risk warning
- Human approval gate
- Common failure and recovery
- Verification and next action

Screenshots will be focused crops or responsive panels with numbered callouts,
captions, and meaningful alternative text. Dense tables will either reflow as
labelled cards or sit in an intentional, clearly indicated table scroller.

Every lesson will support keyboard navigation and platform text scaling.
Dialog, search, result list, article, outline, images, and icon-only actions will
have accessible names. Body text and focus treatments must meet WCAG 2.1 AA.

## Search and contextual help

Search will build an in-memory index of titles, headings, paragraphs, control
aliases, workspace names, and known error phrases. Each result displays:

```text
Lesson · heading
Highlighted matching excerpt
Workspace / agent breadcrumb
```

Selecting a result opens the exact anchor. Search must remain local, free, and
fast; it must not call an AI provider.

A central help manifest will map:

```text
workspace → agent → tab → control object name → lesson → anchor
```

The same manifest will drive navigation metadata, contextual `?`/F1 help,
search aliases, “Open this in Imprint” actions, and coverage tests. This is the
main defence against UI/documentation drift.

## Scientific income standard

Every metric or recommendation must carry two independent labels.

**Evidence type:** `OBSERVED`, `DERIVED`, `ESTIMATE`, `PROXY`, `HYPOTHESIS`,
`MODEL-GENERATED`, `DEMO`, or `UNAVAILABLE`.

**Data sufficiency:** `Incomplete`, `Descriptive only`, `Comparable`, or
`Replicated`.

Generic “high confidence” labels based only on row count are not allowed. Rates
show their numerator and denominator. Cross-currency totals require an explicit
FX rate and date. Periods must be comparable and imports must be checked for
overlap. Gross or net receipts cannot be called profit without matching costs.
Demo data, trend scores, competitor activity, and model output cannot be called
demand.

Every saved metric should be able to expose an evidence passport:

```text
Metric; evidence type; source; observed at; window; population;
numerator; denominator; currency and FX date; exclusions/missing data;
comparison; allowed interpretation; prohibited interpretation.
```

The Income Lab will include seven local, deterministic worksheets:

1. cash and economic contribution, including owner hours × chosen hourly value;
2. break-even price/units and maximum affordable acquisition cost;
3. funnel stage rates, drop-off, and proportion intervals;
4. baseline-versus-variant comparison with a minimum meaningful effect;
5. recurring cohort retention and contribution without invented lifetime value;
6. effective cost per accepted AI output, including retries and correction time;
7. automation payback and promotion gate with exception and rollback costs.

Scenario inputs will be prominently labelled hypothetical, never forecasts.
Worked examples will include raw inputs, calculation, uncertainty, a tempting
wrong conclusion, the correct next decision, and a failure case. The four core
labs end with an experiment card, economics sheet, decision, and automation
eligibility result.

Automation cannot advance merely because one paid action occurred. Promotion
also requires complete costs, acceptable quality/rework, replication in a
comparable window, observability, spend/stop controls, a tested manual fallback,
and human approval at irreversible, rights, consent, identity, publishing, and
money-moving steps.

## Content source of truth

Replace the hard-coded `PAGES` list with `LearnModule` metadata stored in one
manifest. Minimum fields:

```text
id, section, order, title, summary, outcome, audience, difficulty,
estimated_minutes, prerequisites, workspace, agent, tab, keywords,
updated_at, source_version, filename
```

Agent labels, tab names, control aliases, and capability facts should be derived
from app-owned catalogs where possible. Agent Academy pages remain human-written,
but tests compare their declared coverage against the manifest and live object
names. The main README links to this canonical curriculum instead of maintaining
a competing page count and summary.

## Delivery sequence

### Phase 0 — accuracy and contracts

- Correct stale setup, key, Best Fit, OnlyFans, launcher, and agent-guide claims.
- Remove or qualify Music income projections and invalid confidence language.
- Define `LearnModule`, the help manifest, evidence taxonomy, metric dictionary,
  content block syntax, and learning/content lint rules.
- Add failing coverage tests before expanding content.

Exit: the current Learning Centre is factually aligned with the visible app and
there is one machine-checkable source for curriculum structure.

### Phase 1 — Learning Centre shell

- Build home/goal entry, grouped navigation, compact lesson view, responsive
  drawer, in-page outline, breadcrumbs, recent lesson, and real search results.
- Persist guided progress and the last page/anchor.
- Add keyboard, focus, accessible-name, and text-scaling behavior.

Exit: users can find an exact control/error and read comfortably at supported
window sizes without horizontal prose scrolling.

### Phase 2 — Foundations and contextual bridge

- Publish the six Foundations modules.
- Wire F1/context help from every workspace, tab, provider/model selector, paid
  action, and major error state.
- Add “Open this in Imprint” navigation to the target agent/tab/control.

Exit: every common shell action is taught from both the Learning Centre and its
point of use.

### Phase 3 — Agent Academy

- Build the ten standardised agent modules.
- First wave: OnlyFans, Creator, Publish, Social, Video, Draft.
- Second wave: Audiobooks, Music, Site Builder, Client Gigs.
- Regenerate annotated/cropped images for important tabs and states.

Exit: every visible user-facing control has a valid lesson anchor and each agent
has a verified small workflow, output interpretation, and done condition.

### Phase 4 — Income Lab and tools

- Add evidence passports, metric dictionary, seven worksheets, four guided
  labs, experiment ledger templates, decision rules, and automation gate.
- Clearly mark which measurements Imprint can calculate now and which require
  manual input until product instrumentation is available.
- Add calculator golden tests and claims-policy lint across learning content,
  agent guides, and income-related system prompts.

Exit: a user can move from a hypothesis to a recorded decision without a
forecast, fabricated denominator, hidden labour cost, or ambiguous evidence.

### Phase 5 — playbooks, polish, and release gate

- Compose canonical lessons into end-to-end guided paths.
- Add quality/safety reference, troubleshooting decision trees, glossary,
  templates, change notes, and advanced tools.
- Complete visual regression, packaging, screenshot freshness, accessibility,
  performance, and link/anchor audits.

Exit: the Learning Centre meets every acceptance criterion below in the live
launcher and packaged app.

## Acceptance criteria

- Searching a control or error returns heading-level results with page,
  breadcrumb, snippet, and anchor, and opens the exact match.
- Every visible workspace, agent, tab, provider/model selector, paid action, and
  major error state maps to a valid lesson anchor.
- Every operational lesson has an outcome, prerequisites, steps, verification,
  output interpretation, common failures, and next action.
- Every Agent Academy module covers all controls declared for that agent and
  contains a worked run, objective quality checklist, costs, cancellation,
  safety, handoff, and done condition.
- BEST FIT documentation distinguishes best provider overall from best model
  inside the manually selected provider and explains exclusions, availability,
  budget effects, confidence, setup targets, and sensible overrides.
- At 980×680, 1280×840, and 1600×1000 there is no horizontal scrollbar in prose
  or standard lesson layouts. Navigation collapses at the defined breakpoint
  without losing article position.
- Keyboard-only operation covers search, results, outline, previous/next,
  checklists, contextual launch, navigation drawer, and close.
- The UI remains usable at 100%, 125%, 150%, and 200% text scale; focus and
  contrast meet WCAG 2.1 AA.
- Every referenced instructional image is generated, current, captioned,
  non-orphaned, and mapped to the correct workspace/tab/state.
- Income worksheets label observed, derived, estimated, hypothetical, proxy,
  model-generated, demo, and unavailable data correctly; raw counts and periods
  stay visible; scenarios are never presented as forecasts.
- Golden tests cover all worksheet formulas, currency/period refusal states,
  evidence-label preservation, and automation promotion blocks.
- Content lint rejects unqualified profit/LTV/earnings claims, passive or
  guaranteed-income wording, and demo/proxy/model output presented as demand.
- Last lesson, anchor, guided checklist, and progress survive close/reopen.
- Search responds within 100 ms and the centre opens within 300 ms on the
  supported local baseline.
- The entire Learning Centre, manifest, images, and templates are bundled in the
  packaged application and verified through the live launcher.

## Work boundary

This plan deliberately separates curriculum expansion from the product/data
work that stronger income conclusions eventually require. The curriculum will
not pretend that Imprint currently has per-asset reach, buyer cohorts, complete
cost attribution, retention cohorts, cross-currency normalization, or causal
experiments. Where those fields are unavailable, the lesson and worksheet will
say so and accept explicit manual observations. Product instrumentation can be
added in a separate, reviewed phase after the teaching and metric contracts are
stable.
