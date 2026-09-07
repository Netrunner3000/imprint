# Create & Publish

Create & Publish is a focused desktop AI studio for taking creative work from an idea to a finished, sellable asset. It keeps the dependable local-first platform inherited from Sentinel—multiple model providers, explicit spend permissions, budgets, history, and run logs—while presenting only publishing workflows.

## Workspaces

| Workspace | Tools | Outcome |
|---|---|---|
| **Write** | Draft, Publish | Plan and write books, export manuscripts, prepare distribution, create marketing assets, and track sales work. |
| **Audio** | Audiobooks, Music | Convert books to narrated MP3s and plan music releases, distribution, and promotion. |
| **Web** | Site Builder | Generate responsive HTML, CSS, and JavaScript for author, product, and client sites. |
| **Gigs** | Client Gigs | Produce logo concepts, service listings, and professional client delivery messages. |

Recent work is kept in the project rail. The right-hand control centre shows model routing, system health, estimated spend, budget limits, and run history.

## Product principles

- **Focused:** six creative tools, grouped by the outcome they produce.
- **Local first:** Ollama can run supported workflows without sending prompts to a cloud provider.
- **Spend aware:** cloud calls require explicit session permission and pass through cost and budget checks.
- **Provider neutral:** OpenAI, Anthropic, DeepSeek, Kimi, Gemini, Qwen, and Ollama share one routing layer.
- **Desktop native:** PySide6 and SQLite; no server or external database is required.
- **Project oriented:** history is presented as recent projects rather than a generic chat archive.

## Quick start

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The app opens in **Write → Draft**. Local Ollama models work without API keys. To use a cloud provider, copy the example environment file and add only the keys you need:

```bash
cp .env.example .env
```

Cloud access remains disabled in the interface until the matching provider permission is enabled for the session.

## Core workflows

### Draft

- Create fiction or non-fiction projects.
- Define audience, genre, tone, point of view, and publishing path.
- Generate outlines and chapters.
- Continue, revise, and inspect chapter structure.
- Export to EPUB, DOCX, or PDF.

### Publish

- Import and review publishing metrics.
- Track distributors and platform status.
- Maintain publishing tasks.
- Extract shareable quotes.
- Build a content calendar and short-form promotional assets.

### Audiobooks

- Accept PDF, EPUB, TXT, and MOBI source books.
- Select voice and chunk settings.
- Estimate narration cost before conversion.
- Generate MP3 narration with progress and cancellation support.

### Music

- Plan a single, EP, album, or mixtape release.
- Compare distribution approaches.
- Build rollout, promotion, and income plans.

### Site Builder

- Generate sites from a brief and visual direction.
- Choose Vanilla, Tailwind, or Bootstrap output.
- Review responsive behavior and copy or save generated code.

### Client Gigs

- Generate logo concepts and visual prompts.
- Draft marketplace listings.
- Prepare client-facing delivery messages.
- Track current orders and estimated generation cost.

## Safety and cost controls

Every model-backed workflow goes through a shared request guard:

1. Resolve provider and model.
2. Estimate request cost.
3. Validate agent permissions and budget.
4. Ask for cloud-spend confirmation when required.
5. Start the run log.
6. Record real usage, save project history, and close the run.

The system monitor is non-critical. If macOS or a sandbox blocks a telemetry reading, the app displays a safe fallback instead of failing to launch.

## Data locations

In development, editable configuration and data live in the repository under `config/` and `data/`.

In a packaged macOS app, writable state lives in:

```text
~/Library/Application Support/Create & Publish/
```

This identity is deliberately separate from Sentinel AI, including its single-instance key, so the two applications never share data or block one another from opening.

## Tests

```bash
pytest -q
```

The suite covers the creative agents, book pipeline, cost calculation, provider timeouts, request authorization, usage recording, concurrency behavior, focused registry, and resource-monitor fallbacks.

## Build the macOS application

```bash
./scripts/build_app.sh
```

The PyInstaller definition is `CreateAndPublish.spec`. To install the built application locally, use:

```bash
./scripts/install_app.sh
```

## Repository map

```text
agents/       Creative workflow and prompt construction
config/       Agent registry, tools, commands, pricing, and settings
services/     Providers, budgets, persistence, exports, and media pipelines
ui/           Shared widgets, styling, dialogs, tooltips, and workers
tests/        Automated and manual verification
main.py       Desktop shell and workflow panels
```

## Current scope

Create & Publish intentionally excludes Sentinel's research, security, Wi-Fi, betting, and agent-factory verticals. Their instructions may remain in historical planning documents, but they are not part of this product or its active registry.
