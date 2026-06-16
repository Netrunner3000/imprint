# BLOODHOUND — Deep OSINT Dossier

## What it does
Bloodhound is the deep-investigation OSINT agent. It builds a comprehensive, structured intelligence dossier on a target — a person, username, email, domain, or organisation. The output is significantly more detailed than TRACE: it assigns a **threat level**, calculates a **confidence score**, offers **scope controls**, and adds advanced tradecraft tool recommendations alongside image metadata hints.

Like TRACE, Bloodhound is a **planning layer** — it does not perform live lookups. It produces a research-grade dossier that tells investigators exactly what to pursue and how.

---

## How to use

1. **Enter a target** (person name, username, email, domain, or organisation).
2. *(Optional)* **Add context** — any known details: location, employer, known aliases, linked accounts.
3. *(Optional)* **Select scope** — controls how broad or narrow the dossier should be.
4. *(Optional)* **Enable image metadata** — includes reverse image search strategies and EXIF analysis hints.
5. **Select a Provider & Model** — Anthropic or OpenAI strongly recommended for the structured multi-section output.
6. Click **Investigate**.

---

## Output sections

| Section | Contents |
|---|---|
| Executive Summary | One-paragraph overview with threat level (LOW / MEDIUM / HIGH / CRITICAL) and confidence score (0–100 %) |
| Identity Matrix | Full breakdown of names, aliases, accounts, and corroborating data points |
| Digital Footprint | Social profiles, forums, paste sites, breach data, public posts |
| Network & Infrastructure | Domains, IPs, WHOIS, DNS records, certificate transparency logs |
| Tradecraft Tools | Specific tool recommendations (Maltego, Spiderfoot, Sherlock, etc.) with usage notes |
| Threat Assessment & Next Steps | Prioritised action plan, risk indicators, and recommended investigation sequence |

---

## Threat levels
- **LOW** — minimal public exposure; routine monitoring sufficient
- **MEDIUM** — moderate footprint; targeted follow-up warranted
- **HIGH** — significant exposure or anomalies; active investigation recommended
- **CRITICAL** — severe exposure or indicators; immediate action required

---

## Confidence score
Ranges from 0 to 100 %. Reflects how much data was available to support the dossier. A low confidence score means the target has a thin online footprint — treat conclusions cautiously.

---

## Tips
- Enable **image metadata** when you have a profile photo or image associated with the target — it generates EXIF extraction commands and reverse-image search strings.
- Use **scope: narrow** for a fast first pass; use **scope: full** when preparing for a formal investigation.
- Bloodhound prompts are long — use a model with a large context window (`claude-sonnet-4-6`, `gpt-4o`).

---

## See also
**TRACE** — the lightweight query planner. Use it first for a quick sweep; escalate to Bloodhound when depth is needed.
