# 1 · Start here

> **Outcome:** in fifteen minutes you will configure one safe provider route,
> create one project, generate one useful asset, and know where it was saved.

Imprint is a production system for AI-assisted income work. It joins research,
creation, packaging, distribution drafts, costs, and owned performance data in
one place. It can remove repeated labour. It cannot prove demand, approve a
claim, accept a client delivery, or guarantee revenue for you.

The operating loop is:

`Observe demand → choose one offer → produce → review → distribute → measure → improve`

Automation belongs **after** the first version of this loop has evidence. The
fastest way to waste money is to automate output before anyone has wanted it.

## Know the shell

| Region | What it controls | Use it well |
|---|---|---|
| **Project rail** | New Project and your saved projects. | Keep one project per product, offer, client order, or venture. |
| **Workspace tabs** | Write, Audio, Video, Social, Web, Gigs, Creator, OnlyFans. | Choose the business stage first; then choose the tool inside it. |
| **Tool switcher** | The agents available in that workspace. | Draft creates; Publish packages; the other workspaces specialise. |
| **Provider / Model** | Which AI service performs the current task. | Start with **Use Recommended**. Change models only for a measured reason. |
| **Estimate / Spend** | Expected request cost, last cost, session and daily totals. | Set caps before a long job. Treat “not priced” as unknown, not free. |
| **System / Routing / API keys** | Readiness and diagnostic state. | Look here first when a button is disabled or a provider is missing. |

![The Write workspace](img/workspace-draft.png)

## Four things to configure once

### 1. Provider access

Open **Settings** and add only the keys you intend to use. The private file is
stored under `~/Library/Application Support/Imprint/`; never paste keys into a
project, prompt, exported document, or chat. Expand **API KEYS** in the right
rail to confirm what Imprint can actually reach.

### 2. Permissions

Provider access and permission are separate. A stored key says Imprint *can*
contact a service; the permissions row says it *may* do so in this session.
Keep unused providers off. This makes routing predictable and prevents an
automatic route from using an account you did not mean to spend from.

### 3. Budget limits

Open **Limits** and set both caps:

- **Session limit** contains one focused working session.
- **Daily limit** contains all Imprint requests for the day.

Text requests use token estimates. Images, speech, and video may be billed by
image, character, duration, or a provider quote. Imprint reserves the shown
amount before submission. An unknown price is visibly labelled; check the
provider before proceeding.

### 4. Project context

Create a project and fill the fields that describe the product. For a book,
complete **Title**, **Author**, **Type**, and **Book Profile**. Other tools have
their own brief fields. Good reusable context is the difference between a
connected production line and a pile of unrelated generations.

## Your first proof-of-work

Do this before designing a large automation:

1. Choose **Write → Draft**.
2. Create a project named `Learning test`.
3. Set a session limit you are comfortable spending.
4. Click **Use Recommended**, then **Estimate Cost**.
5. In **Direction**, write one bounded request: “Draft a 150-word product
   description for a weekly meal-planning template aimed at busy students.”
6. Select the closest **Task**, then press **Write**.
7. Edit one sentence in the output. Generated work is meant to be edited.
8. Press **Save Draft** and confirm the project persists after switching away.
9. Open **Cost History** and find the request.

Success is not “the AI wrote something.” Success is that the input, output,
cost, location, and next decision are all known.

## How to read cost information

| Label | Meaning |
|---|---|
| **Estimated Request Cost** | A preflight reserve based on the chosen model and request. It is not an invoice. |
| **Last Request Cost** | The best post-request amount Imprint can record. Provider reporting may still differ. |
| **Session / Daily** | Recorded spend against your two guardrails. |
| **Cost not priced yet** | Imprint has no trustworthy local rate for this action. Investigate before spending. |

For external asynchronous jobs, cancellation does not necessarily erase a
charge. Once a provider has accepted a render, Imprint may need to wait and
save the result even if the local screen is closed.

## Choose your next chapter

- Learn a screen or button: [Controls & agents](02-agents.md)
- Decide what to sell: [Income science](03-profit.md)
- Connect tools into a repeatable loop: [Automation playbooks](04-workflows.md)
- Something is not working: [Troubleshooting](07-troubleshooting.md)
