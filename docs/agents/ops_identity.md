# OP IDENTITY — Operational Identity Manager

## What it does
Op Identity is an operational security (OPSEC) and identity management tool. It helps researchers, investigators, and privacy-conscious users manage research email accounts, track which tools and platforms those accounts are registered on, and store associated API keys and credentials in an organised, local-only vault.

> **Privacy note:** All data stored in Op Identity is saved locally on your machine only — nothing is transmitted to any server.

---

## How to use

### Managing Research Identities
1. Click **+ New Identity** to create a new operational identity.
2. Enter a label (e.g. "Research-01", "Honeypot-Finance"), the associated email address, and any notes.
3. The identity is saved and appears in the identity list.

### Tracking Tool Registrations
For each identity, you can log which tools and platforms it's registered on:
1. Select an identity from the list.
2. Click **+ Add Registration**.
3. Enter the platform name, URL, registration date, and account status.
4. Registrations are displayed as a table under the identity — useful for auditing exposure.

### Storing API Keys
1. Select an identity or use the global **API Keys** section.
2. Click **+ Add Key**.
3. Enter the service name, key value, and any notes.
4. Keys are stored locally and can be revealed or hidden with the eye icon.

---

## Use cases

| Scenario | How Op Identity helps |
|---|---|
| OSINT research | Separate email per investigation; track which platforms it's registered on |
| Bug bounty | Dedicated test accounts per program; log registration dates for scope compliance |
| Privacy research | Multiple identities with distinct footprints; track cross-contamination |
| API key management | Central store for all research-related API keys across providers |

---

## Tips
- Use **distinct labels** that don't reveal the purpose — "Research-01" is better than "BountyHunting-Email".
- Regularly **audit registrations** — deactivate or delete accounts on platforms you no longer use to reduce your attack surface.
- Store API keys with **expiry notes** so you know when to rotate them.
- Keep identities **strictly separated** — never use a research identity for personal accounts or vice versa.
