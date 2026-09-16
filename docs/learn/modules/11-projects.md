# Projects, saving, and exports

> **Outcome:** create one clean project, know which information belongs to it,
> save authoritative work explicitly, and recover the exported result.

## Prerequisites

- You know the buyer, asset, client order, or venture this work belongs to.
- You understand that **Remove** is destructive from the app's perspective;
  save/export anything needed first.

## One project, one durable context

Create a separate project for each sellable output, client order, campaign, or
venture. Reusing one project for unrelated work contaminates prompts, makes
search ambiguous, and disconnects cost or run history from the business object
you intended to measure.

## Walkthrough

1. Press **New Project** and perform the smallest initial save available in the
   chosen agent.
2. Rename the project by double-clicking its row in the project rail. Use a
   stable name such as `Client — deliverable — date`.
3. In Draft, save the **Book Profile** separately from **Save Draft**. Profile
   fields become reusable context; the editor is the authoritative manuscript.
4. In agents with **Save**, **Export**, **Save as File**, or **Save Full Plan**,
   treat that button as the boundary between generated workspace content and a
   deliverable outside the editor.
5. Use **Show in Finder** or **Open Output Folder** when provided. Do not assume
   every agent shares one output directory.
6. Switch projects and return. Verify the expected fields/output restore before
   removing or overwriting anything.
7. Before **Remove**, export or copy the approved result and confirm its file.

## Persistence boundaries

| State | Safe assumption |
|---|---|
| Visible generated text | Unsaved until the agent's save/project behavior is verified |
| Explicit Save/Save Draft | Stored in the agent/project data path |
| Export/Save as File | Written to the chosen or documented external location |
| Provider-hosted media URL | Temporary until Imprint downloads it successfully |
| Clear | Removes visible working content; it is not undo |
| Remove project | Do not expect recovery through the UI |

## Verification

- [ ] The project restores after switching away and back.
- [ ] The approved deliverable opens from its actual file location.
- [ ] Project context contains no unrelated client, persona, or product data.
- [ ] Temporary/provider-hosted output has been downloaded before expiry.

## Common failures

**The wrong text returned:** confirm the project and explicit save boundary.  
**A file is missing:** use [Files, launcher, and recovery](15-files-recovery.md).  
**Two projects look identical:** rename them by business object and date; never
use the first prompt as the only identifier.

## Next action

Before generating, learn [Providers, models, and Best Fit](12-best-fit.md) and
[Costs, estimates, and limits](14-costs-limits.md).
