# Imprint technical reference

Imprint is an umbrella studio: each agent owns a focused production workflow,
while the shell supplies shared navigation, providers, model recommendations,
budgets, history, storage, and recovery. Use this reference when you need to
understand **what a control changes, where work is stored, which service a task
uses, or why a run did not complete**.

For step-by-step teaching, screenshots, and income experiments, open the
**Learning Centre**. Docs are the precise reference; Learning is the guided
course.

## Start with the right reference

| Need | Open |
|---|---|
| Learn an agent from the beginning | Learning Centre → Agents |
| Understand every input and output | This Docs centre → the agent sheet |
| Choose a provider or model | Learning Centre → Best-fit recommendations |
| Diagnose a stopped or failed run | Agent sheet → Requirements and failure modes |
| Understand files, keys, costs, or privacy | This page → Shared systems |
| Test whether a workflow makes money | Learning Centre → Income Lab |

The Docs button in the header opens the sheet for the agent currently visible.
The general Docs button opens this overview. Both use the same searchable
reference centre, so a search for an exact control name can jump directly to
the matching heading.

## How Imprint is organised

An agent is an independent project under `agents/<agent>/`. It owns its prompts,
recommendation profile, specialist services, tests, and project README. The
umbrella app owns only the shared seams needed to operate all agents together.

1. **Workspace navigation** selects an outcome area such as Author,
   Audio + Music, or Video + Ads.
2. **Agent controls** collect the task brief and production settings.
3. **Best fit** ranks eligible providers and models for that exact agent and
   context. It is a recommendation, not a guarantee.
4. **The request gate** checks availability, permissions, and budget before a
   paid or remote call begins.
5. **The agent** builds the provider request and validates the response.
6. **Storage and history** keep outputs, settings, and measured usage in the
   writable Imprint data directory.

Each agent sheet names its inputs, output locations, execution path,
requirements, and deliberate limitations. That boundary matters: a selectable
model should have a real execution route, and sample data must never be
presented as live evidence.

## Shared systems

### Providers and models

Provider and model menus show capabilities that the selected agent can use.
The **Provider best fit** badge compares providers; the **Model best fit** badge
compares models inside the selected provider. A setup-target recommendation
means the option fits the task but is not configured yet. It should not be read
as ready to run.

Local Ollama work stays on the machine. Cloud providers require both a key and
permission in the current execution mode. Image, video, voice, and text models
are kept in separate capability catalogs so a text model cannot appear in a
video menu merely because the vendor offers both.

### Costs and limits

The Spend rail shows the current session, today, request count, last request,
and remaining room against the session and daily limits. A pre-flight estimate
reserves conservatively; the usage record is corrected when the provider
returns measured usage. A zero or unavailable estimate is not proof that a
service is free—confirm the provider's current pricing before production runs.

### Routing

Routing records the last agent, provider, and model used. The recommendation
card separately reports the current best fit, score, confidence, and whether
setup is required. These are intentionally distinct: the last route is an
observation; best fit is a decision aid that can change with task, budget,
privacy, or availability.

### API keys

Keys are loaded from the environment or Imprint's user-data `.env` file. The
right rail reports only **Configured**, **Not configured**, or **Check failed**;
it never displays the secret. A configured key still may lack billing, quota,
model access, or regional availability, so the first real request remains the
final capability check.

### Files and persistence

Development runs use the project data directory. The packaged macOS app uses
`~/Library/Application Support/Imprint/` for writable data so launching from
Finder does not depend on a working directory inside the app bundle. Agent
sheets identify their exact output folders and database records.

Do not treat the source folder and the installed `.app` as interchangeable. A
development launcher can run current source immediately; a separately copied
or packaged application must be rebuilt to contain new bundled resources.

## A reliable operating loop

### Before a run

- State one concrete deliverable and its audience.
- Confirm the selected agent and task tab.
- Check the provider/model recommendation and whether it is ready.
- Review the estimated cost, remaining budget, output folder, and any external
  account requirement.
- Keep source rights, consent, platform rules, and claims inside the brief.

### During a run

- Watch the stage or status line rather than clicking the action repeatedly.
- Use Stop when the result is no longer useful or the input is wrong.
- Treat partial files as incomplete until the agent's verification step passes.

### After a run

- Verify the output against the brief and the agent sheet's acceptance checks.
- Save or export the final version to the stated output location.
- Record measured cost, time, traffic, conversion, and revenue separately from
  model-generated estimates. An **observed transaction** belongs in the ledger;
  a hypothetical price or conversion rate belongs in the experiment record.
- When a workflow repeats, automate only the stable steps and retain human
  review at publishing, spending, consent, and account-risk boundaries.

## Failure triage

| Symptom | First check | Next reference |
|---|---|---|
| Action is disabled | Required field, file, key, or selection | Current agent → Inputs |
| Menu is empty | Provider availability or capability catalog | Current agent → Requirements |
| Run stops immediately | Key permission, quota, budget, or validation | Spend, API keys, Run Log |
| Output is blank or partial | Status log and output folder | Current agent → How it works |
| Result is polished but unreliable | Source, freshness, evidence label | Learning Centre → Evidence |
| Installed app looks old | Launcher target versus current source/build | Learning Centre → Files & recovery |

When reporting a problem, include the active agent, task, provider/model, the
exact status or error text, and whether the source or packaged app was opened.
Never include an API key.

## Documentation contract

Every public agent must have one searchable sheet that covers purpose, inputs,
outputs, execution path, storage, requirements, extension points, and material
limitations. New controls should be named exactly as they appear in the app so
search can find them. Workflow teaching belongs in the Learning Centre and is
linked from here instead of copied.

Docs are bundled with the app and work offline. Provider names, prices, quotas,
and platform policies can change; the agent sheets describe Imprint's current
integration, while live commercial terms must be verified with the provider.
