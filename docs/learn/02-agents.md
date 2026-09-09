# 2 · The agents, one by one

Six agents across four modes. Each one has a `Docs` button that opens its own
reference sheet from `docs/agents/`; this page is the working guide.

---

## Write → Draft  *(author)*

![Draft](img/workspace-draft.png)

Long-form drafting: outlines, characters, scenes, dialogue, world-building.

| Control | Use it for |
|---|---|
| `Direction:` | What to write **next**. One concrete instruction beats a paragraph of context. |
| `Task:` | The shape of the output — Write Scene, Outline, Character, and so on. |
| `Draft / Outline / Characters / World Notes / Chapters` | Separate documents that persist per project. |
| **Write** | A fresh pass from the Direction box. |
| **Continue** | Extends the existing draft. Use this far more than Write. |

**Working method that holds up:** outline first in the Outline tab, then write
scene by scene with a one-line Direction each time. Long prompts asking for
"chapter 3" produce mush; "the argument in the kitchen, she leaves angry"
produces a scene.

The word and scene counters are live — useful when a publisher wants 80,000
words and you need to know where you stand.

---

## Write → Publish  *(author, publish page)*

![Publish](img/workspace-publish.png)

Turns a finished draft into the documents publishing actually asks for:
synopsis, blurb, query letter, one-page pitch.

`Comp Titles` matters more than it looks. "Gone Girl meets Dark Places" tells
the model the shelf, the tone and the reader in four words, and it is the field
most people leave blank.

---

## Write → Publish & Market → Market  *(author, market page)*

![Market](img/workspace-market.png)

Store-facing copy: Amazon description, launch posts, newsletter copy. `Platform`
changes the format — an Amazon description and a social post are not the same
text with different lengths.

---

## Publish  *(manuscript)*

![Publish agent](img/agent-manuscript.png)

Sales tracking and the publishing todo list.

- **Ingest KDP CSV** — Amazon has no public API, so royalties arrive as CSV
  reports you download from KDP. This reads them into the app's database.
- **Refresh Data** / **Period** — the metrics view over what has been ingested.
- **Publishing Todos** — a seeded checklist per platform (KDP, Draft2Digital,
  IngramSpark, PublishDrive).
- **Ask about your book** — questions answered against your own ingested numbers.

---

## Audio → Audiobooks  *(audiobook)*

Converts an ebook (PDF / EPUB / TXT / MOBI) into MP3 via OpenAI TTS.

Costed per character, so a full novel is not trivial — check the estimate before
starting. The conversion runs as a separate process and can be stopped.

**Note:** the panel opens a dialog if its input folder holds no supported ebook.
Point it at a folder with real files before selecting it.

---

### Listening to what you made

![The Listen tab](img/agent-audiobook-listen.png)

The **Listen** tab is the library: every audio file in your output folder, with
progress and position. Select one and the button reads *Resume at 1:24:03* — it
picks up exactly there.

Position is remembered per file and saved while you listen, not only when you
stop, so closing the laptop mid-chapter does not lose your place. A book played
to the end is marked finished and starts over next time rather than resuming
three seconds from the end. **Start Over** resets one deliberately.

---

## Audio → Music  *(music)*

![Music](img/agent-music.png)

Release planning rather than audio generation: artist profile, release setup,
distributor comparison, Spotify pitch, income roadmap.

Output marks **[AI OUTPUT — COPY-PASTE READY]** against **[HUMAN ACTION
REQUIRED]**, so you always know which parts you still have to do yourself.

---

## Web → Site Builder  *(webdesign)*

![Site Builder](img/agent-webdesign.png)

HTML/CSS/JS generation with the result split across `HTML`, `CSS` and `JS` tabs
plus a line count.

Fill in `Colour Palette` and `Framework` — left blank, the model picks for you,
and its default taste is generic.

---

## Gigs → Client Gigs  *(fiverr)*

![Client Gigs](img/agent-fiverr.png)

Logo concepts, gig descriptions, and client delivery messages.

**Generate Logos** is the paid, headline action — it bills per image, and that
now counts against your budget caps. Pick the **Image model**: `dall-e-3` is
the long-standing default, `gpt-image-1` is newer and noticeably better at text
inside an image, which is most of what a logo is. **Delivery Message** and
**Gig Description** are text-only and cheap. The Orders tab tracks what you
produced for whom.

---

## Video → Video  *(video)*

![Video](img/agent-video.png)

Topic in, finished video out: script, narration, aligned captions, generated
visuals, Ken Burns motion, music and a thumbnail. This is the `vidforge`
pipeline running inside Imprint — the same code as the standalone app, not a
copy, so a render started in either shows up in both libraries.

**Format** is the only decision that changes the shape of the run:

| | |
|---|---|
| **Long-form** | Whatever `config.yaml` says — 1920×1080, aimed at ~8 minutes. For YouTube. |
| **Social clip** | Vertical or square, 15–90 seconds, cut roughly every 6 seconds. For TikTok, Reels, Shorts. |

The estimate beside the button is real: it comes from the pipeline's own
per-stage arithmetic (images, narration characters, caption alignment) and is
charged against your session and daily caps before the run starts. A long-form
video is typically €1–2; a 30-second clip about €0.25. Most of that is images.

**Stop** cancels at the next stage boundary rather than mid-ffmpeg, so you are
never left with a half-written file. A cancelled run stays in the Library and
can be resumed.

![Video library](img/agent-video-library.png)

---

## Social → Social  *(social)*

![Social](img/agent-social.png)

The funnel for everything else in the studio. A **campaign** is one subject —
a book, a release, a product, a gig — and its goal. Posts are written per
platform, laid on a schedule, and either posted directly or copied out.

Write for the platform, not for "social media". The same announcement is a
different piece of writing on each one, and not because of length: Reddit
removes posts that read as marketing, Pinterest is a search engine wearing a
mood board, X gives you seven words before someone scrolls. That guidance is
built into each platform's prompt.

**Angle** matters more than most people expect. `launch` is the one everyone
reaches for and the one that works least often; `behind_the_scenes`, `excerpt`
and `value` all give someone a reason to read who was not already going to buy.

**Make a Clip** is where Video and Social meet: it writes a topic brief, hands
it to the video pipeline at the right aspect and length for the platform, and
files the finished mp4 against the campaign. You are not maintaining two video
workflows.

**Schedule Drafts** spreads undated drafts across the coming weeks at each
platform's own cadence — seven a week on X, one a week on Reddit. That last
number is not timidity: posting more often than that on Reddit is how accounts
get banned, whatever the API allows.

### What can actually post

![Social accounts](img/agent-social-accounts.png)

Writing works everywhere. Posting does not, and the Accounts tab is honest
about which is which:

| | |
|---|---|
| **YouTube, Reddit, Pinterest** | Can post today. Each needs credentials you can obtain yourself — see the tab for exactly which. |
| **X, Instagram, TikTok, Threads, LinkedIn** | Drafting only. Each needs a paid tier, a linked business account, or an app review that Imprint cannot obtain on your behalf. |

Nothing posts on its own. There is no scheduler running in the background and
no "publish all" — the schedule is a plan you work through, one confirmed click
at a time. That is deliberate: a tool that posts unattended is how an account
gets banned for something its owner never saw.

---

## Creator → Creator  *(creator)*

![Creator](img/agent-creator.png)

Planning and drafting for subscription creator accounts: content calendar,
captions, PPV copy, welcome messages, off-platform promos, and earnings.

**It does not post.** OnlyFans has no usable API, and the tools that fake one
get accounts permanently banned — so this drafts and you send. That is also the
only kind of automation their terms allow: the kind that assists a human rather
than replacing one.

| Tab | What it holds |
|---|---|
| Draft | The generated copy, editable. |
| Calendar | What is queued, and what each item earned once you record it. |
| Earnings | Imported statements, price points that actually converted, top content. |
| Voice | The account's own writing samples — the single biggest lever on quality. |
| Media | Photosets, clips, and anything Higgsfield rendered. |
| Agency | Every account side by side, for managed work. |
| Records | That age and identity documents exist for anyone depicted, and where. |

**Fill in Voice first.** Paste five of the account's own posts. Everything the
agent writes afterwards imitates them, and without that step the drafts are
competent and completely generic — the difference is larger than any other
setting in the app.

Accounts are typed **own**, **managed** or **persona**. A managed account —
someone else's, run on their behalf — will not draft until you record who
authorised it. A persona carries a character bible and a locked seed so it stays
one character instead of becoming a new one each session.

`Generate Teaser` renders promo video through Higgsfield. It is safe-for-work
by construction: Higgsfield prohibits explicit material and moderates prompts,
reference images and outputs, so explicit content has to come from elsewhere.
Its role is the teaser that lives on X or Reddit.

---

Next: [Making money with it](03-profit.md)
