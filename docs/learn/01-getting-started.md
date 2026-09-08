# 1 · Getting started

The whole app is one loop: **set up a project once → produce with an agent →
publish it → market it.** Everything else is detail.

![The Draft workspace](img/workspace-draft.png)

## The four regions

| Region | What it is for |
|---|---|
| **Left rail** | Your projects. A project is the thing you are making — a book, a release, a client job. |
| **Mode tabs** (Write · Audio · Web · Gigs) | Which kind of work you are doing. Each mode holds one or two agents. |
| **Centre** | The agent itself: its inputs on the right, its output on the left. |
| **Right rail** | What this is costing you, and the three dialogs you actually open. |

The right rail keeps `SPEND (€)` open because it is the one thing worth
watching mid-run. `SYSTEM`, `ROUTING` and `API KEYS` are collapsed: they are
reference material for when something looks wrong.

## Before your first run

1. **Add an API key.** `⚙ Settings`, or edit `.env` in
   `~/Library/Application Support/Create & Publish/`. The `API KEYS` section in
   the right rail shows which providers are live.
2. **Check your budget.** `SPEND (€)` → `Session` and `Daily`. Defaults are €1
   and €5. A request that would exceed either is refused before it is sent, not
   after.
3. **Fill in the Project Bar** — Title, Author, Type. Everything downstream
   reuses it, so doing it once saves repeating yourself in every panel.
4. **Open Book Profile and click Save Profile.** The hook and target reader
   shape every prompt the book agents build.

## Reading the cost line

Before each run, `Estimated Request Cost` shows what the request will cost at
the selected provider and model. It is an estimate from token counts; the
`Last Request Cost` line afterwards is the billed figure.

If both read `€0.00` for a paid provider, that provider has no pricing row —
see [Best practices](05-best-practices.md#money).

## A first run, end to end

1. **Write → Draft.** Fill Title/Author/Type, save the Book Profile.
2. Put one instruction in `Direction:` — "opening scene, protagonist misses
   the last train" — pick a `Task`, press **Write**.
3. Edit the result directly in the draft pane. It is a normal text editor.
4. **Continue** extends from where the draft ends rather than starting over.
5. **Write → Publish** turns the draft into a synopsis, blurb or query letter.
6. **Publish & Market → Market** writes the Amazon description and launch copy.

That is the loop. Every other agent is the same shape with different inputs.

---

Next: [The agents, one by one](02-agents.md)
