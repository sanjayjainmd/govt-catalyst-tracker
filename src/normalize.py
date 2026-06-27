"""Common catalyst schema + helpers. Every feed produces records in this shape."""
import hashlib
import datetime


def make_id(*parts):
    raw = "|".join(p or "" for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _utcnow():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def base_record(**k):
    """Build a normalized catalyst record. Feeds fill the source-specific fields;
    resolve/score/route fill ticker, materiality, score, and decision."""
    return {
        "id": make_id(k.get("source"), k.get("url"), k.get("title")),
        "source": k.get("source"),
        "first_seen": k.get("first_seen") or datetime.date.today().isoformat(),
        "last_updated": _utcnow(),
        "url": k.get("url"),
        "program": k.get("program"),
        "agency": k.get("agency"),
        "recipient_legal": k.get("recipient_legal"),
        "ticker": None,
        "beneficiaries": [],
        "amount": k.get("amount"),
        "amount_type": k.get("amount_type"),
        "sector": k.get("sector"),
        "stage": k.get("stage"),
        "quality_tier": k.get("quality_tier"),
        "materiality_ratio": None,
        "market_cap": None,
        "pop_end": None,          # period-of-performance end date (awards)
        "active": None,           # True if pop_end is in the future
        "dissemination": "primary",
        "title": k.get("title"),
        "tier1_hit": False,
        "score": 0.0,
        "decision": "log",
    }
