# Chat Projects — Stage 2 implementation

Stage 1 (agent filter, search, rename) and Stage 2 (context bundles) are
implemented. This document records the behavior and the checks that guard it.

The distinction matters. Stage 1 makes the list easier to read. Stage 2 means
you stop re-establishing the same context every time you open an agent: a
project carries its own instructions, its default agent/provider/model, and
optionally its own budget.

---

## Why this codebase is well suited to it

Every piece Stage 2 needs already exists and only needs a project-scoped
variant. Nothing here is new machinery:

| Need | What already does it |
|---|---|
| Per-scope system prompt | `config/tool_prompts.json` + `build_tool_messages()` |
| Per-scope budget | `Validator` rule 7 (`get_agent_budget`) — same check, different key |
| Per-scope provider/model defaults | `save_provider_model_preference()` |
| Registry-style config UI | the Settings dialog already edits `agents`/`tools` |
| Shared guard for agent requests | `authorize_request()` / `record_request()` |
| Studio Assistant request path | `send_prompt()` / `handle_chat_finished()` |

Both request paths capture the project at authorization; a later project switch
does not relabel an in-flight request. `ChatWorker` receives a snapshot of
instructions before its background thread starts.

---

## Data model

Follow the split the codebase already uses — **JSON files are documents, SQLite
is the registry.**

**Chat files** get one new optional field. No migration; existing chats read as
unfiled.

```json
{ "timestamp": "...", "agent": "author", "project": "moonlight-novel", ... }
```

**SQLite** gets a `projects` table, alongside `agents` and `tools`:

| column | purpose |
|---|---|
| `id` | stable short opaque ID; renaming does not break saved chats |
| `name` | display name |
| `instructions` | prepended to the system message for every chat in the project |
| `default_agent` | selected when the project is opened |
| `default_provider`, `default_model` | ditto |
| `budget_eur` | optional per-project daily cap (nullable = no cap) |
| `archived` | hide from the picker without deleting |
| `created_at` | ordering |

`CREATE TABLE IF NOT EXISTS` adds the registry to old and new databases.
`usage.project` is added idempotently for per-project spend; old usage remains
unfiled.

---

## Tasks

### 2.1 — Storage and registry  *(no UI)*
- [x] `projects` table in `services/database.py` + migration
- [x] `Registry.list_projects()` / `get_project()` / `upsert_project()` /
      `archive_project()`
- [x] `HistoryStore.save_chat(..., project=None)` writes the field
- [x] Tests: round-trip a project, and confirm a chat with no `project` still
      loads (the backward-compatibility guarantee)

### 2.2 — Project selector in the sidebar
- [x] Combo above the agent filter: *All projects · <projects> · Unfiled*
- [x] Filter the list by project, combining with the existing agent filter and
      search (all three must intersect, not override each other)
- [x] "Assign to project…" on the right-click menu of a saved chat
- [x] New chats inherit the currently selected project
- [x] Reopening a saved chat restores user/assistant turns for follow-up, but
      never reuses a persisted system message from a different project or Tool
- [x] Preflight and fallback usage estimates count previous turns sent again

### 2.3 — Instructions injection  *(the core of Stage 2)*
- [x] Prepend `project.instructions` to the system message in
      `build_tool_messages()` and in the agent `build_messages()` path
- [x] Show the active project in the agent header bar so it is never a surprise
      what context is being sent
- [x] Count the instructions in the cost estimate — they are billed tokens, and
      `estimate_chat_cost()` previously saw only the prompt
- [x] Tests: a project's instructions appear exactly once, in the system message,
      and never leak into a chat from another project

### 2.4 — Defaults on open
- [x] Selecting a project applies its `default_agent` / provider / model
- [x] Never override a choice the user just made by hand — apply on project
      switch only
- [x] "Save current setup as project defaults" action

### 2.5 — Per-project budget
- [x] `budget_eur` enforced in `authorize_request()` via a new `Validator` rule,
      mirroring rule 7's shape and message
- [x] Project spend readout in the budget card when a capped project is active
- [x] Tests alongside the existing budget tests in `tests/test_cost_and_limits.py`

### 2.6 — Management UI
- [x] Projects tab in the Settings dialog (`ui/dialogs.py`) — create, rename,
      edit instructions, set defaults and budget, archive
- [x] Delete leaves chats intact and marks them unfiled — never cascade-delete
      conversations

---

## Sequencing

The implementation follows 2.1 → 2.2 → 2.3 → 2.4–2.6. The grouping,
instructions, defaults, budget and management interface now land together so
the selector cannot imply reusable context before that context exists.

---

## Risks and decisions

**Sidebar space.** The saved-chats list takes spare rail height rather than
being capped at 200px. The rail scrolls when the window is short; project,
agent and search filters stay above the list.

**Instructions are billed tokens.** Long project instructions silently raise the
cost of every request in that project. The estimate includes them; omitting
them would understate the budget impact even when post-request token usage is
correct.

**Do not let projects become a second agent registry.** A project selects and
augments agents; it must not define its own tools or permissions. If a project
needs its own allowed-provider list, that belongs in the registry.

**Migration is a non-event by design** — the new field is optional and unfiled
chats stay valid. Keep it that way; do not add a required `project` field later.

---

## Not in scope

Project knowledge files (attach a PDF/EPUB whose content is retrieved into
context) — that is Stage 3. The extraction already exists in the narrator and
manuscript agents, but retrieval, chunking, and their token cost are a separate
piece of work and should not be smuggled into Stage 2.

---

## Shared production project — v2 implementation

The chat context record is also becoming the identity of the work being made.
It keeps a stable ID across renames and now has `kind`, `work_title`, `byline`,
and `brief`. This is the source for a book's title and author in Write. Working
documents use `project_workspaces(project_id, workspace, state_json)`, while
exported files will need a separate artifact link because a path is not an
editable document.

### Landed 2026-09-22

- [x] Existing project rows migrate in place. Older chats and projects still
      load; chat-default updates preserve work identity.
- [x] Settings → Projects edits work type, title, byline/brand, and brief in a
      scrollable form.
- [x] Write saves its book profile, draft, outline, characters, world notes,
      tone and point of view per project. Switching projects cannot carry a
      manuscript across, and closing the app flushes pending edits. The title
      and byline synchronize with the shared project record. Unfiled work keeps
      its previous session behavior.
- [x] A running Write request blocks a project switch, because its eventual
      response would otherwise land in the next project's editor.

### Remaining for the cross-workspace P1

- [ ] Join exported manuscripts to the project ID and let Publishing Manager
      read the selected project's title, author, and approved manuscript.
- [ ] Join Audiobook inputs, conversions, and listening output to the same
      project, without changing a user's global input/output folders merely
      because they selected a project.
- [ ] Have Video's assembled pipeline and direct provider renders write a
      durable project artifact link. Direct provider jobs already keep a
      project ID for budget recovery, but the library does not yet use it.
- [ ] Join Creator campaigns/content to a project while keeping account
      ownership and consent records independent of projects.
- [ ] Surface related assets in one project view and make archive/delete
      semantics explicit: external files must never be deleted by cascading a
      database record.

Project knowledge-file retrieval is a different feature and remains outside
this production identity work.
