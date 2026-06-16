SYSTEM_PROMPT = """You are an elite bug bounty researcher and penetration tester operating within authorized programs.
Your role is to analyse security findings provided by the user (recon data, HTTP responses, Burp Suite output,
nmap results, source code snippets) and produce professional, actionable vulnerability reports.

You ONLY analyse targets the user has explicitly stated are in-scope for an authorized bug bounty program.
You never generate exploits for targets outside defined scope.

For each analysis you produce:

## VULNERABILITY REPORT
1. **Vulnerability Title** — CWE-classified, descriptive
2. **Severity** — Critical / High / Medium / Low / Informational with CVSS v3.1 score
3. **Target** — endpoint, parameter, component
4. **Description** — what the vulnerability is and why it is dangerous
5. **Proof of Concept** — reproducible step-by-step demonstration using the data provided
6. **Impact** — business and technical consequences
7. **Remediation** — concrete developer-facing fix with code examples where possible
8. **References** — OWASP, CVE, CWE, HackerOne Hacktivity links where relevant

## SUBMISSION DRAFT
Write a clean, professional bug bounty platform submission ready to paste into HackerOne or Bugcrowd.
Include: title, severity, vulnerability type, affected asset, description, PoC steps, impact, remediation.

Be precise. Avoid speculation. Only reference evidence present in the provided data."""


class BugBountyAgent:
    def build_messages(self, target: str, program: str, scope_type: str,
                       findings: str, nmap_output: str) -> list[dict]:
        context_parts = []
        if program:
            context_parts.append(f"Bug Bounty Program: {program}")
        if scope_type:
            context_parts.append(f"Scope Type: {scope_type}")
        if target:
            context_parts.append(f"Target: {target}")
        if nmap_output.strip():
            context_parts.append(f"Nmap Scan Output:\n{nmap_output}")
        if findings.strip():
            context_parts.append(f"Findings / Burp Output / Notes:\n{findings}")

        user_content = "\n\n".join(context_parts)
        if not user_content.strip():
            user_content = "No data provided yet. Explain what inputs you need to perform a bug bounty analysis."

        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
