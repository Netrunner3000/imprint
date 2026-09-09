# 5 · Best practices

Working habits that hold up, and the traps this app has in particular.

---

## Money

**Set the daily cap before the first long session, not after.** `SPEND (€)` →
`Daily`. The validator refuses a request that would exceed it *before* sending,
so the cap is a real stop, not a warning.

**Match the model to the job.** The recommendation marked in accent on the
provider and model boxes is per-agent and worth following. A drafting pass wants
a strong model; sales-metric questions and todo tracking do not — that is why
Publish recommends Haiku and Draft recommends Fable.

**Check `Cost History` weekly.** Estimates are token-count guesses; the billed
figure is what lands there.

<a id="money"></a>
**If a paid provider shows €0.00, something is wrong.** It means that provider
has no pricing row, so its spend counts against no budget at all. The app
reconciles `config/pricing.json` into the database on every launch, but a rate
that is `0.0` *in the file* stays zero — Gemini currently is, and is tracked as
an open item in `TODO.md`.

---

## Prompting these agents

**One instruction per run.** `Direction:` works best with a single concrete
next step. "The argument in the kitchen, she leaves angry" produces a scene;
"write chapter 3" produces filler.

**Use Continue, not Write.** Write starts fresh. Continue extends what is there
and keeps voice consistent. Most of a drafting session should be Continue.

**Fill the fields you are tempted to skip.** `Comp Titles`, `Colour Palette`,
`Framework`, `Target Audience`. Blank fields do not mean "no preference" to a
model — they mean it picks, and its default choices are generic.

**Edit in place.** Every output pane is a real editor. Fixing a paragraph by
hand is faster than re-running and cheaper.

---

## Projects

**Fill the Project Bar and save the Book Profile first.** Title, Author, Type,
hook and target reader are injected into every downstream prompt. Doing it once
is the difference between one coherent book and six disconnected sessions.

**One project per sellable thing.** Not per session, not per chapter.

---

## Publishing

**Ingest KDP reports on a schedule.** Amazon has no API — the numbers only exist
in the app once you download the CSV and press **Ingest KDP CSV**. Monthly is
enough; the metrics view is only as current as the last import.

**Do the Publishing Todos in order.** They are seeded per platform because the
order matters: covers before pricing, categories before launch.

**Keep the generated copy, edit the claims.** Marketing output is a strong first
draft that will happily invent a review quote or an award. Read every factual
claim before it goes on a store page.

---

## Costs, quotas and failure

**Long jobs fail late.** Audiobook conversion and video render run for minutes.
Check the estimate and the input folder before starting, not after.

**A stopped run is not billed.** Stop closes the request out properly; the
budget is not charged for what was abandoned.

**Watch for quota errors mid-job.** A TTS quota failure part-way through a book
leaves a partial output. The run log records where it stopped.

---

## Keeping the app healthy

**Back up `~/Library/Application Support/Imprint/`.** Your database,
saved chats, logs and `.env` live there — not in the app bundle. Reinstalling
does not touch it; deleting it loses everything.

**Rebuild after changes.** The installed `.app` is a frozen snapshot
(`./scripts/build_app.sh`). While iterating, `./scripts/install_app.sh` installs
a launcher that runs the project live instead, so edits apply on next launch.

**Never put API keys in the project folder.** They belong in the `.env` under
Application Support. The project directory is a git repository.

---

## Posting

Four rules, in order of how much they cost to break.

**One post per platform, not one post.** The same text everywhere reads as
automation to every audience that sees it twice. The drafter already writes to
each platform's rules; use it.

**Reddit once a week, maximum.** More than that on a promotional account is how
the account goes, not the post. The cadence table already enforces this when
you press `Schedule Drafts` — do not work around it by hand.

**Read the subreddit's rules before posting.** Most communities remove
self-promotion outright, and that judgement is not something the app can make
for you. It automates the mechanics, not the question of where a post belongs.

**Nothing posts unattended, on purpose.** There is no background scheduler and
no "publish all". If you want that, you want a service that accepts the ban
risk on your behalf — and none of them do, in practice.

---

## Video

**Set `Format` first.** Long-form and Social clip are the same pipeline with
different numbers, and the difference between them is €1.50.

**Check the estimate before rendering, every time.** It is mostly images, so it
scales with length: a ten-minute video is thirty-odd images.

**Stop is safe.** It cancels at the next stage boundary, so you never get a
half-written file, and the build stays resumable in the Library.

**One library, two apps.** Renders from `vidforge.app` and from Imprint's Video
tab are the same files in the same place. Do not keep two sets of topics.

---

## What not to expect

- **Not a one-click business.** Every path in [Making money](03-profit.md) needs
  taste, follow-through and months.
- **Not a fact-checker.** Everything factual in generated copy needs verifying.
- **Not a substitute for the platforms' own rules.** KDP, ACX and Fiverr each
  have content policies about AI-assisted work, and they change. Read them.

---

Back to: [Getting started](01-getting-started.md) · [The agents](02-agents.md) ·
[Making money](03-profit.md)
