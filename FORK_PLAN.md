# Atelier — what this fork is, and what still has to happen

> **Status (as of the "Strip the security verticals" and "Rebrand the fork as
> Create & Publish" commits):** steps 3, 5, and 6 below are done — the six
> non-creative agents and `providers/` are deleted, the app is rebranded
> (`APP_NAME`, `SINGLE_INSTANCE_KEY`, `DB_PATH` all say Create & Publish), it
> has its own `scripts/install_app.sh` / `CreateAndPublish.spec`, and `lab_hub`
> already has a `create_and_publish` launcher entry. `chat` was kept, not
> dropped. Step 4 (tabbed UI reshape — Write / Audio / Web / Gigs) is **not**
> done — the left panel is still the collapsible-category sidebar (General /
> Creative / Gigs) inherited from Sentinel, not tabs; see README.md §3. The
> rest of this file is the original plan, left as written for the record.

Forked from `sentinel_ai` on 2026-08-12, with its full history. At the time
this plan was written it was **a byte-for-byte copy of Sentinel** — nothing
had been stripped yet. That was deliberate: the fork exists so the two can
diverge in parallel without destabilising Sentinel while it is still being
refactored.

Rationale for the split, and why Atelier is tabbed rather than sidebar-driven,
is in `docs/app_split.md` (carried over from Sentinel).

## What Atelier keeps

`author` · `manuscript` · `music` · `webdesign` · `audiobook` · `fiverr`

and the eight services that exist only to serve them:

    services/narrator/            services/quote_graphics.py
    services/book_exporter.py     services/shorts_generator.py
    services/kdp_csv_parser.py    services/content_calendar.py
    services/publishdrive_client.py
    services/course/

Those eight are the reason this fork exists: an application's worth of
publishing code was living inside a security tool.

## What has to be removed

`chat` · `osint` · `osint_heavy` · `wifi` · `bug_bounty` · `manager`
and `providers/` (the OSINT username/domain/email lookup layer).

Approximate verticals to delete, smallest first — the same order the Sentinel
refactor uses, and for the same reason (prove the process on a cheap target):

    osint 227 · manager 245 · osint_heavy 434 · bug_bounty 386 · wifi 477

`chat` is the awkward one. A general assistant is useful in any home app, so
decide whether Atelier keeps its own or drops it entirely. Keeping it means
keeping the whole `normal_panel` machinery.

## Order of work

1. **Do not start until the Sentinel refactor reaches phase 4.** Phase 4 turns
   each agent into a self-contained module, which is exactly the unit that gets
   deleted here. Deleting them by hand from a 9,584-line `main.py` is the same
   untangling done twice.
2. **Take the platform package** once Sentinel extracts it, rather than keeping
   this copy of the provider clients, budget logic and cost tracking. If both
   apps keep their own copies they will diverge — and the way they diverge is
   exactly TODO #1, where one guarded path and twenty unguarded ones drifted
   apart inside a single app.
3. Delete the six non-creative verticals and `providers/`.
4. Re-shape the UI as tabs: Write (author, manuscript) · Audio (audiobook,
   music) · Web (webdesign) · Gigs (fiverr).
5. Rebrand: app name, bundle identifier, icon, `runtime_paths.APP_NAME`
   (currently `Sentinel AI`, which decides the Application Support directory —
   changing it moves where a packaged Atelier keeps its data).
6. Its own `install_app.sh` / `.spec`, and a Lab Hub launchpad entry.

## Traps carried over from Sentinel

- `runtime_paths.APP_NAME` drives the writable data directory. Two apps sharing
  the name would share `~/Library/Application Support/Sentinel AI/`.
- The single-instance guard uses `SINGLE_INSTANCE_KEY = "sentinel-ai.single-instance"`.
  Leave it unchanged and launching Atelier will hand focus to Sentinel instead
  of opening.
- `Registry` reads the **SQLite database**, not `config/registry.json` — the
  JSON is only a seed. Removing an agent means removing the row too.
- The launcher `.app` runs the project's `main.py` live, so it points at
  whichever directory it was installed from. Atelier needs its own.

## Not yet done

See the status note at the top of this file. Step 4 (the tabbed UI reshape)
is the remaining open work in "Order of work".
