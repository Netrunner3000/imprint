# Agent project architecture

Status: implemented foundation, September 2026.

## Goal

Each Imprint agent owns a repo-ready project directory while remaining
composable inside one desktop application.  This follows Sentinel's per-agent
ownership and SONAR's nested-companion precedent without prematurely creating
unpublished nested Git repositories.

## High-level design

```text
Imprint umbrella
├── main.py / ui/             window and remaining panel/workflow composition
├── services/                 shared persistence, providers, budgets, workers
├── agents/catalog.py         roster, labels, workspaces, profile locations
└── agents/<agent>/
    ├── __init__.py           stable public contract
    ├── agent.py              owned domain logic
    ├── panel.py              owned workspace (where extracted)
    ├── recommendations.py    owned task and quality requirements
    ├── README.md             operating boundary
    ├── TODO.md               committed work
    └── SUGGESTIONS.md        candidate work
```

Video deliberately keeps Vidforge as its separately versioned engine.  The
Video package owns Imprint's orchestration boundary, while
`agents/video/studio.py` is the adapter and `vidforge/` remains the companion
repository.  OnlyFans deliberately composes Creator rather than copying its
drafting logic.

## Contracts

- The umbrella imports only package-level APIs such as `agents.author.AuthorAgent`.
- `agents.catalog.AgentSpec` is the only roster and navigation source of truth.
- Each selectable agent owns a recommendation profile; the shared engine ranks
  eligible providers and models from that profile.
- Agent packages may depend on shared services and provider protocols.
- Private implementation modules are not cross-agent APIs.
- Every catalog entry must have README, TODO and SUGGESTIONS documents.
- A packaged application must bundle those project documents.

## Data flow

```text
user action
  -> umbrella panel
  -> agent public API builds/validates domain request
  -> shared request guard authorises provider and budget
  -> shared worker/provider executes
  -> umbrella stores run, usage and project state
```

This keeps money, secrets, persistence and provider retries centralized.  An
agent can be extracted without forking those safety-critical services.

The same boundary applies to recommendations: an extracted agent carries its
requirements, while the host supplies the model catalog, availability, budget,
permissions and ranking policy. See `docs/recommendation_system.md`.

## Trade-offs

- Keeping one parent repository is less autonomous than nested Git repos, but a
  clone remains complete and releases remain atomic.
- Several panels still live in `main.py`; OnlyFans, Music, Site Builder,
  Audiobook and Client Gigs own their panels and workflows. The remaining
  panel and handler extraction is the next phase.
- Shared services reduce drift but mean an extracted agent needs a declared
  Imprint platform dependency.

## Extraction sequence

1. Move flat agent implementations behind package public APIs. **Done.**
2. Move each panel and its handlers into `agents/<key>/panel.py`. **OnlyFans,
   Music, Site Builder, Audiobook and Client Gigs done.
   Remaining panels are incremental work. Extracted panels still expose
   temporary host aliases for shared integrations.**
3. Move purely domain-specific services under their owner; keep cross-agent
   storage, providers, budgets and request guards shared.
4. Move focused tests into each agent project while retaining umbrella contract
   tests.
5. Only then publish selected agents as repositories and attach them as proper
   submodules, preserving history.

## Revisit as the system grows

When two independently released apps consume the same agent, extract a versioned
`imprint-platform` package for provider, budget and host protocols.  Until then,
a second copy would create more drift than independence.
