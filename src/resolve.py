"""Entity resolution — recipient legal name -> ticker + market cap + materiality.

The crosswalk (data/crosswalk.csv) is hand-maintained and grows as new recipients
come through. This is the one piece no feed gives you clean.
"""
import csv
import re

_SUFFIXES = [
    " corporation", " corp", " incorporated", " inc", " llc", " l l c",
    " ltd", " limited", " co", " holdings", " company", " plc",
    " us", " usa", " na", " technologies", " technology",
]


def load_crosswalk(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _norm(name):
    n = (name or "").lower()
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    for suf in _SUFFIXES:
        if n.endswith(suf):
            n = n[: -len(suf)].strip()
    return n


def _candidates(c):
    """Legal name plus any pipe/comma-separated aliases (for subsidiaries)."""
    names = [c["legal_name"]]
    raw = c.get("aliases") or ""
    names += [a for a in re.split(r"[|,]", raw) if a.strip()]
    return [_norm(n) for n in names if _norm(n)]


def resolve(rec, crosswalk):
    """Attach ticker/market_cap/materiality if the recipient matches the crosswalk."""
    if not rec.get("recipient_legal"):
        return rec
    target = _norm(rec["recipient_legal"])
    if not target:
        return rec
    for c in crosswalk:
        if any(cn == target or cn in target or target in cn for cn in _candidates(c)):
            rec["ticker"] = c["ticker"]
            try:
                mc = float(c["market_cap_musd"]) * 1e6
                rec["market_cap"] = mc
                if rec.get("amount"):
                    rec["materiality_ratio"] = float(rec["amount"]) / mc
            except (ValueError, TypeError, ZeroDivisionError):
                pass
            if c.get("sector"):
                rec["sector"] = c["sector"]
            break
    return rec
