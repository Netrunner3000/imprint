# CREATOR — subscription account planning & drafting

`key: creator` · class: `agents/creator_agent.py → CreatorAgent` · panel: `build_creator_panel()` · handler: `creator_generate()`

## What it does
Plans and drafts for subscription creator accounts (OnlyFans and similar):
content calendar, feed captions, pay-per-view copy, welcome messages,
off-platform promos, profile bios, and earnings tracking.

## What it deliberately does not do
**It does not post, and it has no send path.**

OnlyFans has no public API — the limited access introduced in 2024 is for
verified business partners only. Every third-party "OnlyFans API" is browser
automation or a reverse-engineered private endpoint, which their Terms of
Service prohibit; the documented outcome is a permanent ban and lost earnings.
For an account that *is* the income, that is not a trade worth making.

Their terms draw the line themselves, and it is a sensible one: automation that
**assists** a human is fine, automation that **replaces** one is not. So this
agent produces drafts you review and send yourself.

It also will not write a message posing as a specific real person in a live
conversation with a paying subscriber. The drafts are captions, promos and
starting points in your voice — not a stand-in for you.

## Account types
Recorded per account, because the three carry different obligations.

| Type | Meaning | Requirement |
|---|---|---|
| `own` | Your own account | — |
| `managed` | Someone else's, run on their behalf | An **authorisation record** — who approved it and when. Drafting is refused without it. |
| `persona` | A synthetic character you operate | A **disclosure line**. Drafts stay fictional in framing and never assert the persona is a real named human. |

The managed-account check lives on the drafting path (`require_ready()`), not
just in the dialog — a rule enforced only by a UI prompt is not enforced.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Account / Handle / Type | Which account, and under what basis. |
| Authorised by | Managed accounts only. Who consented. |
| Disclosure | Personas only. How the account discloses itself. |
| Draft | post · ppv · welcome · promo · bio · campaign. |
| Price (USD) | PPV only — shapes the value argument in the copy. |
| Promo channel | Promo only — X, Reddit, TikTok, Instagram, Threads. |
| Brief | What it is about. Concrete briefs give non-generic drafts. |
| Provider / Model | Routed through the normal budget guard. |

## Outputs
Three tabs: **Draft** (editable output), **Calendar** (scheduled items you post
by hand — `draft → approved → posted` is a status you set yourself), and
**Earnings** (imported statements).

## Higgsfield promo video
`Generate Teaser` sends a safe-for-work prompt to the Higgsfield API for a
promo clip aimed at the off-platform funnels where subscription traffic
actually originates.

Higgsfield's Terms of Use prohibit **sexually explicit material** and
**unauthorised images of other people**, and moderate prompts, reference images
*and* outputs; circumventing moderation is itself a violation, and breaching it
terminates the account. `services/higgsfield_client.check_prompt()` refuses
those requests locally, before the spend, with a reason — negated mentions
("no nudity") are allowed, since those are instructions to the model rather
than requests for it.

The practical consequence: **explicit content cannot come from Higgsfield.**
Its role here is the teaser, not the product.

## Earnings
`📥 Import Earnings CSV` reads a statement exported from the platform — the
same pattern as the KDP importer, for the same reason: no API, so the numbers
only exist here once you export and import them. Keyed on
`(account, filename)`, so re-importing the same export updates rather than
double-counting.

Column names differ per platform and change over time, so the parser matches
header substrings and stores the raw rows alongside the totals.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/creator_agent.py` | `CreatorAgent`, `require_ready()`, prompt construction. |
| `services/higgsfield_client.py` | Video API client and the content-policy guard. |
| `services/creator_csv.py` | Earnings statement parsing and ingest. |
| `main.py: build_creator_panel()` | Account section, compose section, seven tabs. |
| `main.py: creator_generate()/creator_schedule()/creator_import_earnings()` | Lifecycle. |
| `creator_accounts` / `creator_content` / `creator_earnings` | Tables. |

## Notes
- Nothing here touches the platform. Removing an account removes it from
  Imprint only.
- Adult content platforms have their own rules about AI-assisted material, and
  they change. Read them; this app does not track them for you.
