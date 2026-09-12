# 7 · Troubleshooting

> Start with the visible status, preserve the original error, and test the
> smallest failing action. Repeatedly pressing the paid button is not a retry
> strategy.

## The three-minute diagnostic

1. Read the status line and expand **SYSTEM**, **ROUTING**, and **API KEYS**.
2. Confirm the correct workspace, project, provider, model, and permission.
3. Check session/daily budget room and whether the cost is priced.
4. Copy the exact error before closing anything.
5. Retry with the smallest possible text or one short asset. Do not retry a
   submitted video job until its provider status is known.

## Imprint does not open from the macOS launcher

The installed launcher runs the live project and its virtual environment. It
cannot start if the project folder moved or `.venv` was removed.

1. Confirm the project still exists at the location named in the launcher
   alert.
2. Look at `/tmp/imprint_launch.log` for the most recent startup error.
3. If the project moved, run `scripts/install_app.sh` from the project's new
   location so the launcher records the correct path.
4. If the virtual environment is missing or incomplete, restore the project's
   dependencies, then reinstall the launcher.
5. If Imprint appears active without a window, quit the existing Imprint
   process from macOS and open it once more.

The launcher and a frozen production build behave differently: the launcher
uses live project files; the frozen app uses bundled resources and Application
Support data. Know which one you opened when diagnosing paths.

## A provider or model is missing

| Check | Why it matters |
|---|---|
| Key exists under Settings / API KEYS | No credential means the route is unavailable. |
| Provider permission is enabled | A stored key can still be intentionally disallowed. |
| Refresh Models was pressed | Menus may need to reload after configuration changes. |
| The model performs this media type | Text models are not video/image/TTS endpoints. |
| Required second secret exists | Higgsfield uses both key ID and secret. |
| Correct ecosystem key exists | Wan uses DashScope/Qwen; Veo/Omni use Google/Gemini. |

Use **Model Guide** and the current agent's **Docs**. A model should not be
added to a menu until the app has an implemented request, pricing, polling,
download, and error path for it.

## The action is blocked by budget

- Check both session and daily caps; either can refuse the request.
- Review the estimate, number of concepts, duration, book length, or batch size.
- Reduce the unit of work instead of disabling the guardrail.
- If the label says unpriced, verify the live provider rate before deciding.
- If recorded spend looks wrong, compare Cost History with the provider record.

A cap refusal is a successful safety control, not a failed generation.

## Text output is empty, generic, or in the wrong tab

1. Confirm the brief and reusable profile are not blank.
2. Ask for one bounded deliverable with required sections and constraints.
3. Use **Continue** only when you intend to extend current Draft content.
4. Inspect all output tabs; structured agent responses can route sections.
5. Try a small request with **Use Recommended** to separate prompt trouble from
   route trouble.
6. Preserve the error/status if the stream stopped rather than completed.

If output is coherent but generic, improve the authoritative context. Changing
models before adding audience, source material, acceptance criteria, or examples
usually changes style more than usefulness.

## Video is stuck or Stop appears ineffective

First identify the route:

- **Narrated pipeline:** cancellation occurs at a stage boundary. The current
  stage may finish before stopping.
- **Higgsfield:** cancellation may work while queued; processing jobs may need
  to finish.
- **Sora, Gemini Omni, Veo, or Wan:** the integration may have no safe provider
  cancellation after submission. Imprint keeps polling and saves the paid result.

Keep Imprint and the connection available for provider outputs with temporary
download URLs. Check the Library and output folder before submitting another
job. A disabled Stop button can be an honest indication that the provider has
already accepted non-cancellable work.

## Video fails before rendering

| Symptom | Check |
|---|---|
| vidforge unavailable | The nested `vidforge` project/dependency is present and importable. |
| No topic | Enter a topic or configure the expected topics file. |
| Duration/aspect changes | Select provider/model first; allowed controls adapt to capability. |
| Stock route fails | Pexels key exists and the script/narration providers are also ready. |
| Assembly fails | ffmpeg is installed and the output directory is writable. |
| Direct result missing | Read provider status before retrying; hosted files can expire. |

## Audiobook finds no books or stops part-way

- Point **Input** at a folder containing PDF, EPUB, TXT, or MOBI files, then
  Refresh.
- Confirm OpenAI access; audiobook TTS uses it regardless of the text provider
  selected elsewhere.
- Convert a short sample to verify voice, extraction, and pronunciation.
- Read Output Log for quota, extraction, chunk, and resume information.
- A partial run can leave completed audio/chunks and incurred charges. Inspect
  them before restarting.
- In Listen, use Rescan after moving files. Resume is keyed to the full file
  path, so renaming or moving creates a different library identity.

## Social cannot post

Open **Accounts**. Drafting support and posting support are deliberately
separate. Some platforms require OAuth, a business account, paid API access, or
app review; others remain copy-and-post flows. The tab shows the configured
state, not a promise that platform rules have not changed.

Use Copy Text and Mark Posted when direct publishing is not configured. Never
work around a platform restriction with browser automation or a private API.

## Publisher or Creator metrics look empty

Imprint cannot infer sales that were never imported.

- Refresh PublishDrive only when its key is ready.
- Download and ingest the correct KDP CSV.
- In Creator Earnings, import the platform statement or Record Revenue.
- Confirm the report window, account/profile, currency, and deduplication name.
- Keep source attribution unknown when the report does not supply it.

An empty dashboard can accurately mean “no observed data in Imprint,” not “zero
revenue.” Conversely, a trend score is not a substitute for imported actuals.

## Files are not where expected

- Use the current agent's **Show in Finder**, **Open Output Folder**, or Save
  action when available.
- Development/launcher mode can use project paths; a frozen app redirects
  writable state to `~/Library/Application Support/Imprint/`.
- Search the output library before regenerating an expensive asset.
- Verify an export destination explicitly; do not assume it follows the project.

## What to include in a useful bug report

```text
Imprint launch type: [live launcher / frozen app / terminal]
Workspace and agent:
Project:
Provider and model:
Action and smallest reproducing input:
Expected result:
Observed result and exact error:
Estimate / budget state:
Output or log location:
Whether an external job was submitted:
```

Remove API keys, identity documents, private client content, unreleased work,
and personal earnings rows before sharing a report.

---

Back to [Start here](01-getting-started.md) · Review [Controls & agents](02-agents.md) · Protect the workflow with [Operate safely](05-best-practices.md)
