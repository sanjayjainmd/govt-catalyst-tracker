"""SEC EDGAR feed — catches incentive ANNOUNCEMENTS that aren't yet obligated awards.

Conditional loan commitments, LOIs, price floors, and similar deals are disclosed by
public companies in 8-K filings long before (if ever) the money hits USAspending. This
is the high-value, stage-3/4 signal the award databases can't see — e.g. the DoD Office
of Strategic Capital $725M conditional loan to Energy Fuels (UUUU), June 2026.

Uses EDGAR full-text search (free, no key). SEC requires a descriptive User-Agent.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from normalize import base_record

FTS = "https://efts.sec.gov/LATEST/search-index?q={q}&forms=8-K&startdt={s}&enddt={e}"
UA = {"User-Agent": "catalyst-tracker sanjayja@gmail.com"}

# Curated incentive phrases. (phrase, quality tier, amount type)
PHRASES = [
    ('"Office of Strategic Capital"', 3, "loan"),
    ('"conditional commitment"', 3, "loan"),
    ('"conditional loan"', 3, "loan"),
    ('"Loan Programs Office"', 3, "loan"),
    ('"Defense Production Act"', 4, "grant"),
    ('"CHIPS incentive"', 4, "grant"),
    ('"price floor"', 1, "offtake"),
    ('"offtake agreement"', 1, "offtake"),
]
_AMOUNT_RE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)\s*(billion|million)", re.I)


def _get_json(url):
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            raise


def _ticker_cik(display):
    # "ENERGY FUELS INC  (UUUU)  (CIK 0001385849)"
    m = re.search(r"\(([A-Z][A-Z.\-]{0,5})\)\s*\(CIK\s*(\d+)\)", display)
    return (m.group(1), m.group(2)) if m else (None, None)


def _largest_amount(text):
    best = 0.0
    for m in _AMOUNT_RE.finditer(text):
        scale = 1e9 if m.group(2).lower() == "billion" else 1e6
        best = max(best, float(m.group(1).replace(",", "")) * scale)
    return best or None


def _filing_url(cik, _id):
    accession, _, doc = _id.partition(":")
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{doc}")


def fetch(lookback_days=45):
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    end = date.today().isoformat()
    seen, records = set(), []
    for phrase, tier, atype in PHRASES:
        url = FTS.format(q=urllib.parse.quote(phrase), s=start, e=end)
        try:
            hits = _get_json(url).get("hits", {}).get("hits", [])
        except Exception as e:
            print(f"  ! sec_edgar {phrase}: {e}")
            continue
        time.sleep(0.3)
        for h in hits[:15]:
            src = h.get("_source", {})
            disp = (src.get("display_names") or [""])[0]
            ticker, cik = _ticker_cik(disp)
            if not cik:
                continue
            key = (cik, h.get("_id", "").split(":")[0])
            if key in seen:
                continue
            seen.add(key)
            filing_url = _filing_url(cik, h.get("_id", ""))
            amount = None
            try:
                req = urllib.request.Request(filing_url, headers=UA)
                with urllib.request.urlopen(req, timeout=40) as r:
                    amount = _largest_amount(r.read(300000).decode("utf-8", "ignore"))
                time.sleep(0.2)
            except Exception:
                pass
            company = disp.split("(")[0].strip()
            rec = base_record(
                source="sec_edgar",
                url=filing_url,
                program=f"8-K: {phrase.strip(chr(34))}",
                agency="SEC 8-K filing",
                recipient_legal=company,
                amount=amount,
                amount_type=atype,
                sector="",
                stage=4,
                quality_tier=tier,
                title=f"{company} 8-K — {phrase.strip(chr(34))}",
                first_seen=src.get("file_date"),
            )
            rec["ticker"] = ticker          # ticker comes straight from EDGAR
            records.append(rec)
    return records
