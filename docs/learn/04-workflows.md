# 4 · End-to-end workflows

Recipes that cross agents. Each one is a sellable thing, start to finish.

---

## A novel, from nothing to a store page

1. **New Project** in the left rail. Fill the Project Bar — Title, Author, Type,
   Genre, Tone, POV.
2. **Book Profile → Save Profile.** Hook and target reader. Every prompt after
   this reuses them.
3. **Draft → Outline tab.** Task `Outline`, Direction: the premise in one
   sentence. Edit the result until the beats are right — this is the cheapest
   place to fix structural problems.
4. **Draft tab, scene by scene.** One Direction per scene, **Continue** between
   them. Watch the word counter against your target.
5. **Publish page.** Generate the synopsis and blurb. Fill `Comp Titles`.
6. **Market page.** `Platform: Amazon Description`, then again for launch posts.
7. **Export Book** — EPUB for KDP, DOCX if an editor wants it.
8. Upload to KDP yourself, then work the **Publishing Todos** list.
9. Once sales exist: download the KDP CSV monthly and **Ingest KDP CSV**.

**Where it usually goes wrong:** skipping step 2, then wondering why chapter 9
sounds like a different book.

---

## Launching that novel on social

The book is done and on a store page. This is the part that decides whether
anyone finds it.

1. **Social → New Campaign.** Subject: the title. Subject is a: `book`. Goal:
   what the fortnight is for — "launch week sales", not "awareness". Link: the
   store page.
2. **Write one post per platform, not one post.** Change `Platform` and press
   **Write Posts** again. The prompt changes with it: what works on Reddit is
   removed as marketing if you paste the X version into it.
3. **Vary the angle.** `launch` once, on the day. Then `excerpt`,
   `behind_the_scenes` and `value` for everything else. Six launch posts in a
   row is how a feed gets muted.
4. **Save to Schedule** after editing each batch. Two or three variants per
   platform gives you something to rotate.
5. **Make a Clip** for TikTok and Reels. It writes a brief, hands it to the
   video pipeline vertically at 30 seconds, and files the mp4 against the
   campaign. About €0.25 each.
6. **Schedule Drafts.** Everything undated gets a date at its platform's own
   cadence — seven a week on X, one a week on Reddit.
7. **Work the Schedule tab.** `Post Now` where it is configured, `Copy Text`
   and `Mark Posted` everywhere else.

**Where it usually goes wrong:** posting the same text everywhere, and posting
to Reddit more than once a week. Both are more likely to cost you the account
than to sell a book.

---

## A YouTube video from a topic

1. **Video → Render.** `Format: Long-form`. Type a topic, or leave it empty to
   take the next line of `topics.txt`.
2. Check the estimate beside the button — typically €1–2, most of it images.
   It is charged against your caps before the run starts.
3. **Render Video.** Eight stages, roughly ten to twenty minutes. **Stop**
   cancels at the next stage boundary, and the part-finished build stays in the
   Library so you can resume it.
4. **Library tab → Play** to check it before it goes anywhere.
5. To publish: **Social**, platform `YouTube`, write the description, then
   `Post Now`. Uploads default to private — make it public from YouTube once
   you have looked at it.

**Where it usually goes wrong:** rendering long-form when you wanted a clip.
`Format` is the first thing to set, not the last.

---

## The same manuscript as an audiobook

1. Export the finished book to a folder of supported files.
2. **Audio → Audiobooks**, point the input folder at it.
3. Check the cost estimate. A novel is dollars, not cents.
4. Pick a voice, **Start**, leave it running.
5. Submit to ACX for a 25–40% royalty, or sell direct.

One manuscript now earns twice. The marginal cost of the second product is the
TTS bill and an afternoon.

---

## A logo gig, order to delivery

1. **Gigs → Client Gigs.** Fill Business Name, Industry, Style, Primary Colours
   from the buyer's brief.
2. **Generate Logos** — this is the paid step, about $0.04 an image.
3. Pick the concepts worth showing. Send fewer, better options; three strong
   beats eight mediocre.
4. **Delivery Msg** for the handover note.
5. **Gig Description** once, when you set the gig up — reuse it after that.

**Margin check:** a few cents of images against a $10–$75 order. The constraint
is your review time, not the API.

---

## A single release, planned properly

1. **Audio → Music.** Artist name, genre, release type, distributor.
2. **Generate Plan** → five tabs: profile, release setup, distribution, Spotify
   strategy, income roadmap.
3. Do the **[HUMAN ACTION REQUIRED]** items yourself — distributor signup,
   SoundExchange registration, the Spotify editorial pitch.
4. Paste the **[AI OUTPUT — COPY-PASTE READY]** parts into the distributor and
   Spotify for Artists.

The plan is a checklist, not a release. Nothing ships until you do the human
half.

---

## A landing page for any of the above

1. **Web → Site Builder.** Page Type `Landing Page`, fill Colour Palette and
   Framework.
2. Brief it with the product you just made — the book's hook, the release, the
   service.
3. **Generate**, then take the `HTML` / `CSS` / `JS` tabs.
4. Deploy free on Netlify or Vercel.

Every product benefits from one URL you control and can point ads at.

---

## Stacking it

The compounding version of all of the above:

> Draft a book → publish on KDP → convert to audiobook for ACX → build a landing
> page → write launch copy in Market → sell a companion course on Gumroad.

One body of work, five products, five income lines. That is the reason the
agents live in one app instead of six.

---

Next: [Best practices](05-best-practices.md)
