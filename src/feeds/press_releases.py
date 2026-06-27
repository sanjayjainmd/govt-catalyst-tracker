"""Press-release / news feed via Google News RSS (free, no key).

Catches incentive ANNOUNCEMENTS — agency and company press releases — including deals
that never surface in EDGAR or USAspending: private recipients (e.g. Phoenix Tailings)
and the day-of agency announcement that precedes any 8-K. The recipient/company is
resolved to a ticker downstream by matching the headline against the crosswalk.
"""
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from normalize import base_record

RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
UA = {"User-Agent": "Mozilla/5.0 (catalyst-tracker)"}

# (query, quality tier, amount type, short label)
QUERIES = [
    ('"Office of Strategic Capital"', 3, "loan", "Office of Strategic Capital"),
    ('"conditional loan" (rare earth OR "critical minerals" OR semiconductor OR nuclear OR battery)',
     3, "loan", "conditional loan"),
    ('"Defense Production Act" Title III award', 4, "grant", "DPA Title III"),
    ('"loan guarantee" "Department of Energy"', 3, "loan", "DOE loan guarantee"),
    ('"CHIPS" award semiconductor', 4, "grant", "CHIPS award"),
    ('("price floor" OR "offtake agreement") "critical minerals"', 1, "offtake", "price floor / offtake"),
]
_AMOUNT_RE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)\s*(billion|million)", re.I)


def _largest_amount(text):
    best = 0.0
    for m in _AMOUNT_RE.finditer(text or ""):
        scale = 1e9 if m.group(2).lower() == "billion" else 1e6
        best = max(best, float(m.group(1).replace(",", "")) * scale)
    return best or None


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def fetch(lookback_days=30):
    seen, records = set(), []
    for query, tier, atype, label in QUERIES:
        url = RSS.format(q=urllib.parse.quote(query))
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=40) as r:
                root = ET.fromstring(r.read())
            time.sleep(0.4)
        except Exception as e:
            print(f"  ! press_releases {label}: {e}")
            continue
        for it in root.findall(".//item")[:30]:
            title = it.findtext("title") or ""
            amount = _largest_amount(title)
            if not amount:        # a dollar figure is our signal filter vs commentary
                continue
            key = (int(amount), _norm(title)[:45])
            if key in seen:
                continue
            seen.add(key)
            src = it.find("source")
            records.append(base_record(
                source="press_release",
                url=it.findtext("link") or "",
                program=f"PR: {label}",
                agency=(src.text if src is not None else "press release"),
                recipient_legal=title,        # resolved to a ticker via crosswalk match
                amount=amount,
                amount_type=atype,
                sector="",
                stage=4,
                quality_tier=tier,
                title=title,
                first_seen=None,
            ))
    return records
