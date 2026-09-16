# Files, launcher, and recovery

> **Outcome:** identify which build is running, find its writable data and
> outputs, and recover from a launcher or partial-job failure without paying
> for blind retries.

## Prerequisites

- Preserve the exact visible error and approximate time.
- Do not resubmit an asynchronous video/media job until its provider status and
  local output folder have been checked.

## Live launcher versus frozen app

The installed development launcher runs the live project and its virtual
environment. Opening it after a source change loads current project code once
the previous Imprint process is fully quit. A frozen production app runs bundled
code and uses seeded writable state under `~/Library/Application Support/Imprint/`.

If two launcher results appear, resolve their filesystem paths before removing
anything. Identical names/icons do not prove they point to the same bundle.

## Launcher recovery walkthrough

1. Fully quit the existing Imprint process; closing a window may leave it active.
2. Open the intended launcher once.
3. If it fails, inspect `/tmp/imprint_launch.log` for the newest startup error.
4. Confirm the live project path still exists and its `.venv` remains usable.
5. If the project moved, run `scripts/install_app.sh` from the new project path
   to replace the launcher's recorded target.
6. If a frozen app fails, diagnose its packaged resources and Application
   Support state separately; reinstalling the live launcher is not that fix.

## Output recovery walkthrough

1. Use **Show in Finder** or **Open Output Folder** from the active agent.
2. Check the agent Library/Listen/Schedule view before regenerating.
3. Inspect completed chunks or partial media after a cancelled conversion.
4. Keep temporary provider download URLs from expiring: allow polling and save
   the accepted result when cancellation is unavailable.
5. Use **Run Log** to connect the action, route, error, and output path.

## Backup boundary

Back up the Application Support data and any project/output directories on a
tested schedule. Removing the app does not necessarily remove user data, and
removing a project from the UI is not a backup operation.

## Verification

- [ ] I know whether this is live launcher or frozen code.
- [ ] I can locate the applicable environment/data directory and launch log.
- [ ] I checked partial/library output before retrying.
- [ ] An approved export opens independently of the editor/provider URL.

## Common failures

**Imprint is active but no window appears:** fully quit the process, then reopen
once.  
**Source changed but UI did not:** you may still be running the previous process
or a frozen/duplicate launcher.  
**Resume starts a new audiobook record:** resume identity can depend on the full
path; moving/renaming the file creates a different identity.

## Next action

Return to the relevant Agent Academy module and run its smallest verification
sample before restarting a paid batch.
