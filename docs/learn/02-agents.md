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

Logo concepts via DALL·E, gig descriptions, and client delivery messages.

**Generate Logos** is the paid, headline action — it bills per image. **Delivery
Msg** and **Gig Description** are text-only and cheap. The order log tracks what
you produced for whom.

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
