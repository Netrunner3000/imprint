# BEACON — Wireless Reconnaissance

## What it does
Beacon is a wireless security and reconnaissance agent. It generates Kali Linux command sequences, signal analysis workflows, and network assessment plans for Wi-Fi environments. It is designed for authorised penetration testing, CTF challenges, and wireless security research.

> ⚠️ **Legal notice:** Only use Beacon against networks you own or have explicit written permission to test. Unauthorised access to computer networks is illegal in most jurisdictions.

---

## How to use

1. **Describe the target environment** — e.g. network name (SSID), known security type (WPA2/WPA3), channel, approximate location/setup.
2. *(Optional)* **Specify your hardware** — e.g. Alfa card, internal Wi-Fi adapter, whether monitor mode is available.
3. *(Optional)* **Select a task type** — reconnaissance, handshake capture, deauthentication, signal analysis, report generation.
4. **Select a Provider & Model**.
5. Click **Analyse**.

---

## What Beacon generates

- **Kali Linux command sequences** — `airmon-ng`, `airodump-ng`, `aireplay-ng`, `hashcat`, `hcxtools`, and related commands with flags explained.
- **Scan & enumeration workflows** — step-by-step procedures for discovering networks, capturing traffic, and identifying clients.
- **Signal analysis notes** — channel congestion, interference sources, signal strength interpretation.
- **Security assessment reports** — structured findings with risk ratings and remediation advice.
- **CTF / lab hints** — for known challenge scenarios.

---

## Common use cases

| Use case | What to enter |
|---|---|
| Network audit | SSID, channel, WPA type, number of clients |
| Handshake capture | Interface name, target BSSID, channel |
| Signal mapping | Floor plan description, AP locations |
| Password cracking (authorised) | Captured .hccapx path, wordlist strategy |
| WPA3 assessment | SAE/Dragonfly environment details |

---

## Tips
- Specify your **adapter capabilities** (monitor mode, packet injection) — Beacon tailors commands to what your hardware can do.
- Include **channel information** for more precise scan commands.
- For report generation, describe what you already found — Beacon will structure it into a professional assessment format.
