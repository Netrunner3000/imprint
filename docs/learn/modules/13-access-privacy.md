# Access, permissions, and privacy

> **Outcome:** distinguish credentials from permission and send data only to
> providers you intentionally allow.

## Prerequisites

- Know whether you are running the live project launcher or a frozen app.
- Obtain provider credentials only from the provider's official account flow.
- Never paste a secret into a prompt, project, screenshot, or bug report.

## Three separate states

| State | Meaning |
|---|---|
| Credential exists | Imprint may be able to authenticate to that provider. |
| Provider is permitted | The current execution policy allows that provider to be used. |
| Route is eligible | Credential, permission, capability, availability, and budget checks passed. |

The **API KEYS** rail reports detected readiness. It is not the secret editor.
The generic Studio Assistant exposes local/hybrid/cloud execution policy and
provider permission controls; dedicated agent selectors expose only their real
implemented routes and recommendations.

## Storage boundary

Development/live-launcher mode loads the project environment. A frozen build
uses its seeded writable data area under `~/Library/Application Support/Imprint/`.
Real operating-system environment variables can override file values. Diagnose
which build is running before changing a file.

## Walkthrough

1. Open **API KEYS** and list only status—not secret values.
2. Identify the selected provider and whether the action sends prompt text,
   source files, images, voice references, identity data, or media to it.
3. Keep unused provider permissions off where the control exists.
4. Use local routes when privacy or offline operation is a hard requirement;
   verify the selected model is actually local.
5. Remove secrets and private source data from screenshots/logs before sharing.
6. Treat platform account connection and AI-provider access separately. A model
   can draft a post without possessing a platform publishing token.

## How to read the result

A green key/status indicator shows detected configuration, not policy approval,
account quota, current provider health, or rights to the submitted content.

## Verification

- [ ] I know which provider receives each input type.
- [ ] Only intended providers are permitted.
- [ ] Secrets remain outside prompts, projects, exports, and reports.
- [ ] Identity, consent, client, and unreleased data have an explicit handling rule.

## Common failures

**Key exists but route is missing:** permission, capability, a second secret, or
budget may still block it.  
**A frozen app ignores the project `.env`:** use the frozen data location; do
not assume launcher and packaged builds share configuration.  
**Social drafts work but posting does not:** AI generation and platform OAuth/
API approval are separate integrations.

## Next action

Set spend guardrails with [Costs, estimates, and limits](14-costs-limits.md).
