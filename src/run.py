"""Orchestrator: poll feeds -> normalize -> resolve -> score -> route -> diff -> email.

Run locally:   py src/run.py
In CI:         invoked by .github/workflows/poll.yml on a daily cron.
"""
import json
import sys
import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from normalize import _utcnow            # noqa: E402
from resolve import load_crosswalk, resolve  # noqa: E402
import market_cap  # noqa: E402
from score import score_record           # noqa: E402
from route import decide                  # noqa: E402
import email_digest                       # noqa: E402
from feeds import federal_register, usaspending, sec_edgar, press_releases  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.yml"
CROSSWALK = ROOT / "data" / "crosswalk.csv"
SNAPSHOT = ROOT / "data" / "snapshot.json"
PUBLISH = ROOT / "docs" / "data" / "catalysts.json"
STATUS = ROOT / "docs" / "data" / "status.json"

# Your GitHub Pages URL (live once Pages is enabled).
DASHBOARD_URL = "https://sanjayjainmd.github.io/govt-catalyst-tracker/"
# Email delivery via Gmail SMTP; see status.json for per-run send result.


def apply_tier_overrides(rec, cfg):
    title = (rec.get("title") or "").lower()
    for kw in cfg.get("tier_overrides", {}).get("tier1", []):
        if kw in title:
            rec["quality_tier"] = 1
            rec["tier1_hit"] = True
            rec["amount_type"] = "offtake"
            return


def collect(cfg, crosswalk):
    records, seen = [], set()
    lb = cfg.get("lookback_days", {})

    def add(rec):
        if rec["id"] in seen:
            return
        seen.add(rec["id"])
        apply_tier_overrides(rec, cfg)
        resolve(rec, crosswalk)
        score_record(rec)
        decide(rec, cfg["thresholds"])
        records.append(rec)

    # Discovery feed: Federal Register NOFOs/rules, per program (stage 2 signals).
    for program in cfg["programs"]:
        try:
            items = federal_register.fetch(program, lb.get("federal_register", 7))
        except Exception as e:  # network/API hiccup shouldn't kill the run
            print(f"  ! federal_register / {program['name']}: {e}")
            items = []
        for rec in items:
            add(rec)
        print(f"  + federal_register / {program['name']}: {len(items)} items")

    # Targeted feed: USAspending awards TO tracked companies (the tradable names).
    names = [c["legal_name"] for c in crosswalk]
    try:
        items = usaspending.fetch(names, lb.get("usaspending", 60))
    except Exception as e:
        print(f"  ! usaspending: {e}")
        items = []
    for rec in items:
        add(rec)
    print(f"  + usaspending / {len(names)} tracked recipients: {len(items)} awards")

    # Announcement feed: SEC 8-Ks for incentive deals (conditional loans, offtakes…).
    try:
        items = sec_edgar.fetch(lb.get("sec_edgar", 45))
    except Exception as e:
        print(f"  ! sec_edgar: {e}")
        items = []
    for rec in items:
        add(rec)
    print(f"  + sec_edgar / incentive 8-Ks: {len(items)} filings")

    # Press-release / news feed: agency + company announcements (Google News RSS).
    try:
        items = press_releases.fetch(lb.get("press_releases", 30))
    except Exception as e:
        print(f"  ! press_releases: {e}")
        items = []
    for rec in items:
        add(rec)
    print(f"  + press_releases / incentive announcements: {len(items)} items")
    return records


def dedupe_press(records):
    """Collapse press-release rows for the same event (same ticker + amount) —
    many outlets report one deal. Keep the highest-scoring representative."""
    out, best = [], {}
    for r in records:
        if r["source"] == "press_release" and r.get("amount"):
            k = (r.get("ticker") or "", int(r["amount"]))
            if k in best:
                if r["score"] > best[k]["score"]:
                    best[k].update(title=r["title"], url=r["url"], score=r["score"])
                continue
            best[k] = r
        out.append(r)
    return out


def dedupe_email(rows):
    """One line per event across feeds (e.g. the 8-K and its press release)."""
    seen, out = set(), []
    for r in sorted(rows, key=lambda x: x.get("score", 0), reverse=True):
        k = (r.get("ticker") or r.get("title"), int(r.get("amount") or 0))
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def diff(records, snapshot):
    """Mark records that are new or have advanced a stage since last run."""
    items = snapshot.get("items", {})
    alertable = []
    for rec in records:
        prev = items.get(rec["id"])
        if prev is None or prev != rec["stage"]:
            rec["alert"] = True
            alertable.append(rec)
        items[rec["id"]] = rec["stage"]
    snapshot["items"] = items
    return alertable


def merge_published(records, cfg):
    """Merge into the published file, preserving first_seen and pruning old entries."""
    existing = {}
    if PUBLISH.exists():
        try:
            existing = {c["id"]: c for c in json.loads(PUBLISH.read_text()).get("catalysts", [])}
        except (json.JSONDecodeError, KeyError):
            existing = {}
    for rec in records:
        rec.pop("alert", None)
        if rec["id"] in existing:
            rec["first_seen"] = existing[rec["id"]].get("first_seen", rec["first_seen"])
        existing[rec["id"]] = rec

    # Keep anything still active (regardless of age) plus recently-seen entries.
    cutoff = (datetime.date.today() - datetime.timedelta(days=cfg.get("retention_days", 60))).isoformat()
    kept = [c for c in existing.values()
            if c.get("active") or (c.get("first_seen") or "9999") >= cutoff]
    kept.sort(key=lambda c: (c.get("score", 0), c.get("first_seen", "")), reverse=True)
    return kept


def main():
    cfg = yaml.safe_load(CONFIG.read_text())
    crosswalk = market_cap.apply_live_caps(load_crosswalk(CROSSWALK))
    snapshot = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else {"items": {}}

    print("Polling feeds...")
    records = collect(cfg, crosswalk)
    print(f"Collected {len(records)} records.")

    records = dedupe_press(records)
    usaspending.enrich_active(records, cfg.get("enrich_limit", 60))
    print(f"Active awards: {sum(1 for r in records if r.get('active'))}")

    alertable = diff(records, snapshot)
    send_set = cfg["email"]["send_decisions"]
    to_email = dedupe_email([r for r in alertable if r["decision"] in send_set])
    print(f"{len(alertable)} new/changed, {len(to_email)} qualify for email.")

    prefix = cfg["email"]["subject_prefix"]
    email_sent, email_error = False, None
    try:
        if to_email:
            email_sent = email_digest.send(to_email, prefix, DASHBOARD_URL)
        else:
            # Daily heartbeat so you always know the run happened.
            stats = {"scanned": len(records),
                     "tracked": sum(1 for r in records if r.get("ticker")),
                     "new": len(alertable)}
            email_sent = email_digest.send_heartbeat(stats, prefix, DASHBOARD_URL)
    except Exception as e:  # a mail hiccup shouldn't lose the data commit
        email_error = str(e)
        print(f"email: send failed: {e}")

    kept = merge_published(records, cfg)
    PUBLISH.parent.mkdir(parents=True, exist_ok=True)
    PUBLISH.write_text(json.dumps({"updated": _utcnow(), "catalysts": kept}, indent=2))
    SNAPSHOT.write_text(json.dumps(snapshot, indent=2))
    STATUS.write_text(json.dumps({
        "updated": _utcnow(),
        "scanned": len(records),
        "qualified_for_email": len(to_email),
        "email_sent": email_sent,
        "email_error": email_error,
    }, indent=2))
    print(f"Published {len(kept)} catalysts -> {PUBLISH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
