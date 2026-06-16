"""
Domain OSINT provider — WHOIS, DNS, and certificate transparency.

Zero-cost stack:
  • python-whois  → registrar, dates, nameservers, registrant org/country
  • dnspython     → A, AAAA, MX, NS, TXT, SOA records
  • crt.sh JSON API → certificate transparency subdomain enumeration
"""

import re
import requests


# ── helpers ──────────────────────────────────────────────────────────────────

def _normalize(target: str) -> str:
    """Strip protocol, path, query, port from a domain or IP string."""
    t = target.strip().lower()
    for prefix in ("https://", "http://", "ftp://"):
        if t.startswith(prefix):
            t = t[len(prefix):]
    return t.split("/")[0].split("?")[0].split("#")[0].split(":")[0]


def _is_ip(s: str) -> bool:
    return bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", s))


def _scalar(v) -> object:
    """Collapse whois list values to a single string, cap lists at 5 items."""
    if v is None:
        return None
    if isinstance(v, list):
        items = [str(x) for x in v if x]
        return items[:5] if len(items) > 1 else (items[0] if items else None)
    return str(v)


# ── individual data sources ───────────────────────────────────────────────────

def _whois(domain: str) -> dict:
    try:
        import whois  # python-whois
        w = whois.whois(domain)
        return {
            "registrar":       _scalar(w.registrar),
            "creation_date":   _scalar(w.creation_date),
            "expiration_date": _scalar(w.expiration_date),
            "updated_date":    _scalar(w.updated_date),
            "name_servers":    _scalar(w.name_servers),
            "status":          _scalar(w.status),
            "emails":          _scalar(w.emails),
            "org":             _scalar(w.org),
            "country":         _scalar(w.country),
        }
    except ImportError:
        return {"error": "python-whois not installed — run: pip install python-whois"}
    except Exception as exc:
        return {"error": str(exc)[:300]}


def _dns(domain: str) -> dict:
    try:
        import dns.resolver  # dnspython
        records: dict = {}
        for rtype in ("A", "AAAA", "MX", "NS", "TXT", "SOA"):
            try:
                ans = dns.resolver.resolve(domain, rtype, lifetime=5)
                records[rtype] = [str(r) for r in ans][:10]
            except Exception:
                pass
        return records or {"error": "no records resolved"}
    except ImportError:
        return {"error": "dnspython not installed — run: pip install dnspython"}
    except Exception as exc:
        return {"error": str(exc)[:300]}


def _crtsh(domain: str) -> dict:
    """Query crt.sh for certificate transparency records (subdomain discovery)."""
    try:
        resp = requests.get(
            "https://crt.sh/",
            params={"q": f"%.{domain}", "output": "json"},
            timeout=12,
            headers={"User-Agent": "SentinelAI-OSINT/1.0"},
        )
        if resp.status_code != 200:
            return {"error": f"crt.sh HTTP {resp.status_code}"}

        seen: set = set()
        names: list = []
        for entry in resp.json():
            for name in entry.get("name_value", "").split("\n"):
                name = name.strip().lstrip("*.")
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
        names.sort()
        return {"total_unique": len(names), "sample": names[:30]}
    except Exception as exc:
        return {"error": str(exc)[:300]}


# ── public interface ──────────────────────────────────────────────────────────

def lookup(domain: str) -> dict:
    """
    Return a normalised OSINT dict for a domain or IP address.

    Keys:
      type, query, whois, dns, certificates   (domain)
      type, query, whois, dns                 (IP — crt.sh skipped)
    """
    target = _normalize(domain)
    result: dict = {"type": "domain", "query": target}

    if _is_ip(target):
        result["whois"] = _whois(target)
        result["dns"]   = _dns(target)
    else:
        result["whois"]        = _whois(target)
        result["dns"]          = _dns(target)
        result["certificates"] = _crtsh(target)

    return result
