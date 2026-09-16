# Studio Assistant

> **Outcome:** get one bounded answer, check it against your own acceptance
> criteria, and keep or discard the conversation deliberately.

## Prerequisites

- A question with a concrete deliverable and a way to verify it.
- A local model or an enabled cloud provider with a configured key and enough
  remaining budget.
- A fresh project when earlier conversation context would distract the model.

## Control atlas

| Control | What it changes |
|---|---|
| Tool | Adds the task frame, such as general chat, writing, summary, or rewrite. |
| Command | Inserts an optional reusable prompt scaffold. Check that it fits this request. |
| Provider and Model | Choose the route; Best Fit is guidance, not proof of quality. |
| Mode and API permissions | Limit local/cloud access and which keys may be used. |
| Prompt | The exact request. Include audience, format, constraints, and acceptance test. |
| Send / Stop | Start the guarded request or stop local work; a provider may already have billed. |
| Saved Chats | Reopen a previous thread or create a clean one. |

## Worked run

1. Open **Assistant** and create a new project if the task is unrelated to the
   current conversation.
2. Choose the Tool, Provider, and Model. Inspect the key status, Best Fit reason,
   cost estimate, and session/daily limits before a paid call.
3. Ask for one deliverable and a short list of assumptions. For example:
   “Summarise these notes into five decisions, quote no text not in the notes,
   and mark any unresolved decision.”
4. Press **Send** once. Read the status and Run Log if a result stalls. Do not
   repeat a paid request just because the local status has not refreshed.
5. Check the answer against your input, save the useful output outside the chat
   when it becomes an authoritative asset, and reopen it from Saved Chats.

## How to read the output

The answer is a generated draft. A confident sentence is not an observed fact,
and a suggested price is not a sale. Verify facts and current rules at their
source; use the specialist workspace for production work. Long conversations
send more context to cloud models and can consume more budget.

## Acceptance checklist

- [ ] The answer meets the requested format and includes the required items.
- [ ] Important claims were checked independently.
- [ ] The project can be reopened; any final asset has its own saved copy.
- [ ] The recorded cost is understood as an estimate or measured usage, as labelled.

## Verification

Reopen the saved conversation, compare the response to the prompt and source
material, and inspect the Run Log for its provider, status, and recorded cost.

## Cost, cancellation, and gates

Cloud requests send the conversation context to the selected provider. Local
Ollama requests stay on the machine. Permissions and budget checks run before
the request, but stopping after submission cannot guarantee a provider charge
will be reversed. Keep sensitive source material out of cloud context unless
that disclosure is authorised.

## Common failures

**No model appears:** check the provider key or local Ollama service, then
refresh the model list.
**A request is blocked:** read the exact reason; inspect permissions and budget
before retrying.
**The answer ignores earlier constraints:** start a clean project or restate the
constraint in the current prompt.

## Done when

The answer passes the acceptance checklist, important claims are verified, and
the useful result has a durable saved copy.

## Next action

For production, move the verified brief to the relevant specialist workspace.
For cost and routing decisions, revisit [Costs and limits](14-costs-limits.md)
and [Best Fit](12-best-fit.md).
