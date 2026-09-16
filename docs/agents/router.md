# ROUTER — Intent classifier

`key: router` · class: `agents/router/agent.py → RouterAgent` · panel: **none** — this agent has no workspace

## What it does
Reads a line of text and returns the key of the agent that should handle it. When Auto Route is on, this is what decides that "make a YouTube short about undersea cables" belongs to Video and "write a query letter" belongs to Publish.

It is infrastructure rather than a creative workspace, which is why there is no tab for it. You will only notice it working — or getting something wrong.

## How it decides
A plain substring match, in order. `ROUTES` is a fixed tuple of `(agent_key, keywords)` pairs covering ten modes — onlyfans, video, social, audiobook, music, webdesign, fiverr, creator, manuscript, author — each with a handful of lowercase trigger phrases:

| Agent | Triggers include |
|---|---|
| `video` | video, youtube, shorts, reel, storyboard, sora |
| `manuscript` | query letter, synopsis, kdp, goodreads, book marketing |
| `author` | write a chapter, novel, manuscript, book outline |

`RouterAgent.classify(text)` case-folds the input and returns the first route with a keyword appearing anywhere in it. No match falls back to `"chat"`, which is deliberately not itself a route.

There is **no scoring, no model and no network call.** It is a pure, dependency-free matcher, which is the reason it is instant and free — and the reason it is only as good as its keyword lists.

## What that means in practice
**Order decides ties.** "Write a chapter for my novel and make a video about it" matches both `author` and `video`; whichever route sits earlier in `ROUTES` wins. There is no notion of the better match.

**Substrings match inside words.** A keyword is tested with `in`, not on word boundaries, so a phrase embedded in a longer word still counts.

**It never runs anything.** Routing returns a key. It does not call a provider, does not spend money, and must never bypass the shared request guard — the agent it selects does that work under the usual budget checks.

## When it gets it wrong
Pick the workspace yourself from the mode tabs. Auto Route is a convenience, not a gate, and nothing downstream depends on having been routed rather than chosen.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/router/__init__.py` | Public surface — re-exports `ROUTES` and `RouterAgent`. |
| `agents/router/agent.py` | The whole implementation: the route table and `classify()`. |
| `agents/catalog.py` | The agent keys routing is allowed to return. |
