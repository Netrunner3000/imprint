# SOCIAL — the public funnel

`key: social` · class: `agents/social_agent.py → build_post_messages()` · panel: `build_social_panel()` · storage: `services/social_store.py` · posting: `services/social_publishing.py`

## What it does
Promotes anything the studio made — a book, a release, a product, a gig — across the public platforms. Writes per platform, schedules at each platform's own cadence, and posts directly where the API allows it.

## Why it exists
Every other mode produces something that then needs an audience, and each had grown half a promotion story: Publish schedules quote graphics for books, Creator drafts a single promo post. Nobody owned the funnel itself, and none of it worked for a song or a product.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Campaign / Subject / Subject is a | What is being promoted. The kind (book, release, product, gig) shapes the prompt. |
| Goal / Audience / Link | Context every post is written against. |
| Platform | Which platform's rules and limit to write to. |
| Angle | What the post is *for* — see below. |
| Variants | How many genuinely different versions to write. |
| Write Posts / Make a Clip / Schedule Drafts | The three actions. |

## Angles
A launch announcement and a behind-the-scenes note are different writing jobs, and the drafter treated them as one until these existed:

| Angle | What it produces |
|---|---|
| `launch` | It is out now. Said once. |
| `behind_the_scenes` | How it was made, or what went wrong. The link earns its place. |
| `excerpt` | The best actual line from the work, standing almost alone. |
| `value` | One useful thing, worth reading by someone who never clicks. |
| `question` | Something the audience can answer from experience. |
| `milestone` | A concrete number or moment. Specific, not triumphal. |

`launch` is the one everyone reaches for and the one that works least often.

## Written per platform, not written once
The same announcement is a different piece of writing on each platform, and not because of length. `services/social_platforms.py` carries the guidance per platform and it goes into the prompt verbatim — Reddit removes posts that read as marketing, Pinterest is a search engine wearing a mood board, X gives you seven words. Character limits are checked live in the editor, because models overshoot them and an over-length post is a rejected API call at the worst moment.

## What can actually post
| Platform | Status |
|---|---|
| YouTube | **Can post.** Through vidforge's existing uploader — not a second implementation. Needs an OAuth client secret and one browser sign-in. |
| Reddit | **Can post.** A personal "script" app on your own account; no review needed. |
| Pinterest | **Can post.** Needs a business account, which is free to convert to. |
| X / Twitter | Drafting only — posting needs a paid API tier. |
| Instagram | Drafting only — needs a linked Business/Creator account and a reviewed app. |
| TikTok | Drafting only — direct posting requires passing their audit. |
| Threads | Drafting only — same Meta app model as Instagram. |
| LinkedIn | Drafting only — Share API is granted per app through their partner programme. |

The Accounts tab shows this live, including exactly which environment variables are missing. None of it is verified against the live APIs from the app, and platform terms change often — treat it as a starting point for your own check.

## What it will not do
- **Nothing posts unattended.** No scheduler thread, no "publish all". The schedule is a plan you work through, one confirmed click at a time. A tool that posts on its own behalf while nobody is watching is how an account gets banned for something the owner never saw.
- **No invented evidence.** Reviews, testimonials, sales figures, chart positions and follower counts are forbidden in the system prompt rather than left to chance. A promotion tool that fabricates a happy customer is a liability its owner finds out about last.
- **No engagement bait**, no hashtag walls, no impersonation.

## Cadence
`services/social_store.CADENCE` — posts per week per platform, spread through the week rather than stacked. Reddit is one. That is not timidity: posting more often than that is how promotional accounts get banned, whatever the API allows.

## Cooperation with Video
**Make a Clip** writes a one-sentence topic brief, hands it to the same `produce()` the Video tab uses at the platform's aspect and length, and files the finished mp4 against the campaign. Social owns no rendering of its own — adding video to social cost a prompt, not a second pipeline.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/social_agent.py` | Prompts, angles, variant splitting, limit checks. |
| `services/social_platforms.py` | Per-platform limits, guidance, formats, and what posting really takes. |
| `services/social_store.py` | Campaigns, posts, and the cadence arithmetic. Pure Python, no LLM. |
| `services/social_publishing.py` | The publishers that can actually post, and why the others cannot. |
| `main.py: build_social_panel()` | Campaign, Compose, and the Draft / Schedule / Accounts tabs. |
