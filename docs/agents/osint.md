# TRACE — Light OSINT Query Planner

## What it does
TRACE is a structured open-source intelligence (OSINT) query planner. Given a target — a person, username, email address, domain, or organisation — it generates a ready-to-execute research plan: typed search queries, Google dorks, curated public sources, and a prioritised next-steps summary.

TRACE does **not** perform live lookups or browse the web. It is a planning layer — it tells you exactly what to search and where, so you can execute manually or hand off to an automated pipeline.

---

## How to use

1. **Enter a target** in the Target field (e.g. `john.doe@example.com`, `@johndoe`, `example.com`).
2. *(Optional)* **Add context** — known details about the target that help narrow the search (city, company, role, etc.).
3. **Select a Provider & Model** — Anthropic or OpenAI recommended for structured output quality.
4. Click **Analyse**.
5. Results are split across four output tabs:

| Tab | Contents |
|---|---|
| Query Structure | Typed breakdown of search strings by category |
| Google Dorks | `site:`, `inurl:`, `filetype:` and other advanced Google operators |
| Public Sources | Recommended databases, directories, and platforms to check |
| Summary & Next Steps | Prioritised list of follow-up actions |

---

## Output explained

**Query Structure** — organises queries by type (name, email, username, domain, social, professional). Each entry is ready to paste into a search engine.

**Google Dorks** — precision search operators that surface hidden or indexed content. Copy-paste directly into Google, Bing, or a dorking tool.

**Public Sources** — a curated checklist of relevant platforms (LinkedIn, HaveIBeenPwned, WHOIS registrars, breach databases, social networks, etc.) tailored to the target type.

**Summary & Next Steps** — a short prioritised plan stating which leads are highest value and what to do first.

---

## Tips
- The more context you provide, the more precise the dorks and sources.
- TRACE is fast — it's designed for a quick first sweep before deciding whether a deeper investigation (Bloodhound) is warranted.
- For **email targets**, it automatically generates breach-check and data-broker queries.
- For **domain targets**, it generates WHOIS, certificate transparency, and subdomain enumeration queries.

---

## See also
**Bloodhound** — the heavy OSINT agent. Use it when you need a full six-section dossier with threat level, confidence scores, and advanced tradecraft tool recommendations.
