# BUG SPRAY — Bug Bounty & Vulnerability Triage

## What it does
Bug Spray is a vulnerability triage and reporting agent built for bug bounty hunters and security researchers. Given a vulnerability description or proof-of-concept, it classifies the issue using CWE/CVE taxonomy, estimates CVSS severity, and generates a polished HackerOne-ready submission draft — complete with impact statement, reproduction steps, and remediation advice.

---

## How to use

1. **Describe the vulnerability** — what you found, where (URL/endpoint/component), and how.
2. *(Optional)* **Paste relevant evidence** — HTTP request/response snippets, code fragments, error messages.
3. *(Optional)* **Specify the target program** — HackerOne, Bugcrowd, Intigriti, or private programme.
4. **Select a Provider & Model** — a strong reasoning model (Claude Sonnet, GPT-4o) gives the most accurate CWE mapping.
5. Click **Analyse**.

---

## Output sections

| Section | Contents |
|---|---|
| Vulnerability Classification | CWE ID, CWE name, CVSS score (3.1), severity label |
| Summary | One-paragraph non-technical overview of the finding |
| Technical Details | Root cause analysis, affected component, attack vector |
| Reproduction Steps | Numbered, copy-paste-ready steps to reproduce |
| Impact Assessment | What an attacker could achieve; business risk |
| Remediation | Specific fix recommendations with code/config guidance |
| HackerOne Draft | Full formatted submission ready to paste into the platform |

---

## CWE categories covered
- Injection (SQL, XSS, SSTI, Command, LDAP, XML) — CWE-79, 89, 94, 77, 90, 611 and related
- Authentication & Session — CWE-287, 384, 307, 798
- Access Control — CWE-284, 285, 639, 862
- Cryptography — CWE-327, 330, 916
- Business Logic — CWE-840 and related
- SSRF / IDOR / XXE / Race Conditions

---

## Tips
- The more detail you provide in your description, the more accurate the CVSS score will be.
- Paste the **raw HTTP request** if available — Bug Spray uses it to identify injection points and construct the reproduction steps.
- For **IDOR** findings, include both the victim and attacker account IDs so the reproduction steps are precise.
- Use **"private programme"** as the target if you don't want platform-specific language in the submission draft.
