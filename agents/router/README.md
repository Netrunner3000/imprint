# Router

Internal intent classifier used by the umbrella runtime.  It is infrastructure,
not a visible creative workspace.  Its public API is
`agents.router.RouterAgent`.

Routing should return stable agent keys from `agents.catalog`; it must never
execute provider calls or bypass the shared request guard.

## Files

- `__init__.py` — public surface of the package: re-exports `ROUTES` and
  `RouterAgent` from `agent.py`.
- `agent.py` — the whole implementation. `ROUTES` is an ordered tuple of
  `(agent_key, keyword_tuple)` pairs covering ten modes — `onlyfans`,
  `video`, `social`, `audiobook`, `music`, `webdesign`, `fiverr`, `creator`,
  `manuscript`, `author` — each matched against a handful of lowercase
  trigger phrases (e.g. `video` matches "video", "youtube", "shorts",
  "reel", "storyboard", "sora"; `manuscript` matches "query letter",
  "synopsis", "kdp", "goodreads", "book marketing"; `author` matches "write
  a chapter", "novel", "manuscript", "book outline"). `RouterAgent.classify(
  text)` case-folds the input and returns the key of the first route whose
  any keyword is a substring of it; ordering in `ROUTES` therefore matters
  whenever two routes' keyword lists could both match the same input. If no
  route matches, it falls back to the literal key `"chat"` (not itself an
  entry in `ROUTES`). There is no scoring, no ML model and no external call
  — it is a pure, dependency-free substring matcher.
