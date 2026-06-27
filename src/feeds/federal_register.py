"""Federal Register feed — NOFOs, proposed rules, program guidance (stage 2).

Free public API, no key. https://www.federalregister.gov/developers/documentation/api/v1
These are the earliest official signals: the rules/timing appear here before press releases.
"""
import json
import urllib.parse
import urllib.request
from datetime import date, timedelta

from normalize import base_record

API = "https://www.federalregister.gov/api/v1/documents.json"


def _relevant(text, keywords):
    t = (text or "").lower()
    return any(kw.lower() in t for kw in keywords)


def fetch(program, lookback_days=7):
    since = (date.today() - timedelta(days=lookback_days)).isoformat()
    params = [
        ("per_page", 20),
        ("order", "relevance"),
        ("conditions[term]", '"' + program["keywords"][0] + '"'),
        ("conditions[publication_date][gte]", since),
        ("fields[]", "title"),
        ("fields[]", "abstract"),
        ("fields[]", "html_url"),
        ("fields[]", "publication_date"),
        ("fields[]", "agencies"),
    ]
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "catalyst-tracker"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)

    records = []
    for d in data.get("results", []):
        # Phrase term-search is loose; keep only docs whose title/abstract actually
        # mentions a program keyword. Kills unrelated rules that share a stray word.
        if not _relevant(d.get("title", "") + " " + (d.get("abstract") or ""), program["keywords"]):
            continue
        agencies = ", ".join(a.get("name", "") for a in d.get("agencies", [])) or program["agency"]
        records.append(base_record(
            source="federal_register",
            url=d.get("html_url"),
            program=program["name"],
            agency=agencies,
            recipient_legal=None,
            amount=None,
            amount_type="rule",
            sector=program["default_sector"],
            stage=2,
            quality_tier=program["default_tier"],
            title=d.get("title", ""),
            first_seen=d.get("publication_date"),
        ))
    return records
