# Imprint agent projects

Every directory below is the ownership boundary for one Imprint agent.  It is
small enough to become a standalone repository later, but remains part of the
Imprint repository until it has a real remote and can be attached as a
submodule.  This avoids the broken-clone state caused by ignored nested repos.

## Required shape

```text
agents/<key>/
├── __init__.py       public API imported by Imprint
├── agent.py          usual domain-logic module
├── panel.py          optional owned UI (OnlyFans already uses this)
├── <adapter>.py      optional named runtime adapter (Video uses studio.py)
├── README.md         purpose, boundary and dependencies
├── TODO.md           committed work for this agent
└── SUGGESTIONS.md    ideas not yet committed to
```

The umbrella catalog is `agents/catalog.py`.  It owns ordering and composition;
it must not contain agent implementation logic.  The root `TODO.md` is for
cross-agent platform work only.  Agent-specific work belongs in the agent's own
TODO or suggestions file so Lab tooling can monitor it independently.

## Dependency rule

```text
Imprint shell ──> agents.<name> public API ──> shared services/providers
      │
      └─────────> shared UI, storage, budgets and request guard
```

An agent may use shared services.  It must not import another agent's private
`agent.py`; composition happens in the umbrella.  External callers import from
`agents.<name>`, never from a file inside that package.

## Becoming a separate repository

Do not run `git init` inside an agent directory casually.  First create its
remote, preserve history with a subtree split, then add it to Imprint as a real
submodule.  Until that coordinated step, keeping the packages tracked by the
umbrella means a fresh Imprint clone is complete and runnable.
