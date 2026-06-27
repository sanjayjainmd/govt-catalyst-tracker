"""USAspending feed — awards TO your watchlist companies (recipient-based).

Free public API, no key. https://api.usaspending.gov/
Instead of dumping every grant under an agency (mostly nonprofits/states), this asks
"did any tracked company receive federal money recently?" — which surfaces tradable
names with dollar amounts that drive the materiality score.

USAspending requires award_type_codes from a single group per request, and each group
(grants / loans / contracts) exposes different field + sort names — hence one call each.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from normalize import base_record

URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
DETAIL = "https://api.usaspending.gov/api/v2/awards/"
_BASE_FIELDS = ["Award ID", "Recipient Name", "Awarding Agency", "generated_internal_id"]

# Each group: codes, amount_type label, tier override (None = use agency map), amount field.
AWARD_GROUPS = [
    {"codes": ["02", "03", "04", "05"], "atype": "grant", "tier": None, "amount": "Award Amount"},
    {"codes": ["07", "08"], "atype": "loan", "tier": 3, "amount": "Loan Value"},
    {"codes": ["A", "B", "C", "D"], "atype": "contract", "tier": None, "amount": "Award Amount"},
]

# Awarding agency -> (program label, default quality tier, sector).
AGENCY_MAP = {
    "Department of Commerce": ("CHIPS Act", 4, "semiconductors"),
    "Department of Energy": ("DOE / energy", 3, "energy"),
    "Department of Defense": ("DoD / DPA Title III", 4, "defense"),
    "Department of the Treasury": ("IRA 45X", 2, "clean-energy"),
    "Department of the Interior": ("Critical minerals", 4, "critical-minerals"),
}


def _query(names, codes, amount_field, lookback_days):
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    body = {
        "filters": {
            "time_period": [{"start_date": start, "end_date": end}],
            "award_type_codes": codes,
            "recipient_search_text": names,
        },
        "fields": _BASE_FIELDS + [amount_field],
        "sort": amount_field,
        "order": "desc",
        "limit": 100,
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "catalyst-tracker"},
    )
    # USAspending rate-limits bursts with 503/429 — retry with backoff.
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                return json.load(resp).get("results", [])
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            raise


CHUNK = 8   # USAspending 503s on large recipient_search_text lists (~15+).


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def fetch(names, lookback_days=60):
    """names: list of recipient legal names from the crosswalk."""
    records = []
    for g in AWARD_GROUPS:
        results = []
        for chunk in _chunks(names, CHUNK):
            try:
                results += _query(chunk, g["codes"], g["amount"], lookback_days)
            except Exception as e:
                print(f"  ! usaspending {g['atype']} chunk: {e}")
            time.sleep(0.5)
        for r in results:
            agency = r.get("Awarding Agency") or ""
            program, tier, sector = AGENCY_MAP.get(agency, ("Federal award", 4, "other"))
            if g["tier"] is not None:
                tier = g["tier"]
            gid = r.get("generated_internal_id")
            url = f"https://www.usaspending.gov/award/{gid}" if gid else "https://www.usaspending.gov"
            recipient = r.get("Recipient Name")
            records.append(base_record(
                source="usaspending",
                url=url,
                program=program,
                agency=agency,
                recipient_legal=recipient,
                amount=r.get(g["amount"]),
                amount_type=g["atype"],
                sector=sector,
                stage=4,
                quality_tier=tier,
                title=f"{recipient} — {program} ({g['atype']})",
                first_seen=None,
            ))
    return records


def _pop_end(gid):
    """Award detail endpoint — the search endpoint returns null for PoP dates."""
    url = DETAIL + urllib.parse.quote(gid) + "/"
    req = urllib.request.Request(url, headers={"User-Agent": "catalyst-tracker"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                pop = json.load(resp).get("period_of_performance") or {}
                return pop.get("end_date")
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            return None
        except Exception:
            return None
    return None


def enrich_active(records, limit=60):
    """Fetch period-of-performance end dates for the biggest ticker-matched awards
    and flag whether each is still active (ends today or later)."""
    today = date.today().isoformat()
    todo = [r for r in records if r.get("source") == "usaspending" and r.get("ticker")]
    todo.sort(key=lambda r: r.get("amount") or 0, reverse=True)
    for r in todo[:limit]:
        gid = (r.get("url") or "").rsplit("/award/", 1)[-1]
        if not gid or gid.startswith("http"):
            continue
        end = _pop_end(gid)
        time.sleep(0.2)
        r["pop_end"] = end
        r["active"] = bool(end and end >= today)
    return records
