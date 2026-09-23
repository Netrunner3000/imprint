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

1. Press **New Project**, give it a stable name such as
   `Client — deliverable — date`, and check that its name appears in the header.
2. Open **Settings → Projects**. Set the work type, title, byline or brand, and
   a short creative brief. Add only reusable instructions that really belong
   to this project; optionally set a daily euro cap. Save the current
   agent/provider/model with **Save Current Setup** in the left rail.
3. New chats inherit the selected project. Use **New Chat** for a clean
   conversation in the same project; **All projects** and **Unfiled** have no
   active project context. The project, agent and search filters intersect.
4. Right-click a saved chat to assign it to another project or unfile it.
   Click a saved chat to see its transcript, then type a new follow-up. Earlier
   turns are sent with the follow-up, so longer conversations cost more. The
   current project's instructions replace any old saved system context.
5. In Book Author, the selected project restores its own book profile, draft,
   outline, character and world notes. Edits save after a short pause, on
   project switch, and on app close. **Save Profile** also confirms the shared
   title and byline. **Save Draft** writes a separate text or Markdown file;
   Save Draft and EPUB/DOCX/PDF exports record links to those files under the
   named Project.
6. In Publishing Manager → **Quote Finder**, click **Use Project Draft** to
   copy that Project's current Write draft into the quote source and set the
   byline as attribution. Review the text first: the latest working draft is
   not an approved publication version. You can still use **Load File** for a
   separately approved manuscript.
7. In agents with **Save**, **Export**, **Save as File**, or **Save Full Plan**,
   treat that button as the boundary between generated workspace content and a
   deliverable outside the editor.
8. Use **Show in Finder** or **Open Output Folder** when provided. Do not assume
   every agent shares one output directory.
9. Switch projects and return. Verify the expected chats and defaults before
   removing or overwriting anything.
10. Before **Remove Chat**, export or copy the approved result and confirm its file.

Project instructions are sent to the model and count toward estimated tokens.
They are not a substitute for the agent's own saved profile or an approved
deliverable. A project budget adds a daily guardrail; it does not override the
session/daily limits or external provider invoices.

## Persistence boundaries

| State | Safe assumption |
|---|---|
| Write editor under a named project | Saved to that project's working state after a short pause, on switch, and on app close |
| Visible generated text in other agents | Unsaved until that agent's save behavior is verified |
| Write Save Draft and EPUB/DOCX/PDF export under a named Project | File stored where you choose; Project stores a link to it |
| Other explicit Save actions | Stored in that agent's documented location; Project linking is not yet universal |
| Export/Save as File | Written to the chosen or documented external location |
| Provider-hosted media URL | Temporary until Imprint downloads it successfully |
| Clear | Removes visible working content; it is not undo |
| Archive project | Hides it from the selector; chats remain and can be restored |
| Delete project | Unfiles its chats; removes project identity, working drafts and artifact links, but never deletes external files |
| Remove chat | Deletes the selected chat file after confirmation |

## Verification

- [ ] The project restores after switching away and back.
- [ ] The approved deliverable opens from its actual file location.
- [ ] Project context contains no unrelated client, persona, or product data.
- [ ] Temporary/provider-hosted output has been downloaded before expiry.

## Common failures

**The wrong text returned:** confirm the project and explicit save boundary.  
**A file is missing:** use [Files, launcher, and recovery](15-files-recovery.md).  
**Two chats look identical:** double-click a chat to rename it; project names
are edited under **Settings → Projects**.

## Next action

Before generating, learn [Providers, models, and Best Fit](12-best-fit.md) and
[Costs, estimates, and limits](14-costs-limits.md).
