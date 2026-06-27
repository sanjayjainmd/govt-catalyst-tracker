"""USAspending feed — actual federal awards with dollar amounts (stage 4).

Free public API, no key. https://api.usaspending.gov/
Gives recipient legal name + award amount, which drives the materiality score.
"""
import json
import urllib.request
from datetime import date, timedelta

from normalize import base_record

URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
# Grant/financial-assistance award type codes.
GRANT_TYPES = ["02", "03", "04", "05"]


def fetch(program, lookback_days=30):
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    body = {
        "filters": {
            "time_period": [{"start_date": start, "end_date": end}],
            "award_type_codes": GRANT_TYPES,
            "agencies": [{"type": "awarding", "tier": "toptier", "name": program["agency"]}],
        },
        "fields": [
            "Award ID", "Recipient Name", "Award Amount",
            "Awarding Agency", "Start Date", "generated_internal_id",
        ],
        "sort": "Award Amount",
        "order": "desc",
        "limit": 25,
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "catalyst-tracker"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)

    records = []
    for r in data.get("results", []):
        gid = r.get("generated_internal_id")
        url = f"https://www.usaspending.gov/award/{gid}" if gid else "https://www.usaspending.gov"
        recipient = r.get("Recipient Name")
        records.append(base_record(
            source="usaspending",
            url=url,
            program=program["name"],
            agency=program["agency"],
            recipient_legal=recipient,
            amount=r.get("Award Amount"),
            amount_type="grant",
            sector=program["default_sector"],
            stage=4,
            quality_tier=program["default_tier"],
            title=f"{recipient} — {program['name']} award",
            first_seen=r.get("Start Date"),
        ))
    return records
