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
from score import score_record           # noqa: E402
from route import decide                  # noqa: E402
import email_digest                       # noqa: E402
from feeds import federal_register, usaspending  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.yml"
CROSSWALK = ROOT / "data" / "crosswalk.csv"
SNAPSHOT = ROOT / "data" / "snapshot.json"
PUBLISH = ROOT / "docs" / "data" / "catalysts.json"

# Your GitHub Pages URL (live once Pages is enabled).
DASHBOARD_URL = "https://sanjayjainmd.github.io/govt-catalyst-tracker/"


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
    for program in cfg["programs"]:
        for feed, days in (
            (federal_register, lb.get("federal_register", 7)),
            (usaspending, lb.get("usaspending", 30)),
        ):
            try:
                items = feed.fetch(program, days)
            except Exception as e:  # network/API hiccup shouldn't kill the run
                print(f"  ! {feed.__name__} / {program['name']}: {e}")
                continue
            for rec in items:
                if rec["id"] in seen:
                    continue
                seen.add(rec["id"])
                apply_tier_overrides(rec, cfg)
                resolve(rec, crosswalk)
                score_record(rec)
                decide(rec, cfg["thresholds"])
                records.append(rec)
            print(f"  + {feed.__name__} / {program['name']}: {len(items)} items")
    return records


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

    cutoff = (datetime.date.today() - datetime.timedelta(days=cfg.get("retention_days", 60))).isoformat()
    kept = [c for c in existing.values() if (c.get("first_seen") or "9999") >= cutoff]
    kept.sort(key=lambda c: (c.get("score", 0), c.get("first_seen", "")), reverse=True)
    return kept


def main():
    cfg = yaml.safe_load(CONFIG.read_text())
    crosswalk = load_crosswalk(CROSSWALK)
    snapshot = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else {"items": {}}

    print("Polling feeds...")
    records = collect(cfg, crosswalk)
    print(f"Collected {len(records)} records.")

    alertable = diff(records, snapshot)
    send_set = cfg["email"]["send_decisions"]
    to_email = [r for r in alertable if r["decision"] in send_set]
    print(f"{len(alertable)} new/changed, {len(to_email)} qualify for email.")

    email_digest.send(to_email, cfg["email"]["subject_prefix"], DASHBOARD_URL)

    kept = merge_published(records, cfg)
    PUBLISH.parent.mkdir(parents=True, exist_ok=True)
    PUBLISH.write_text(json.dumps({"updated": _utcnow(), "catalysts": kept}, indent=2))
    SNAPSHOT.write_text(json.dumps(snapshot, indent=2))
    print(f"Published {len(kept)} catalysts -> {PUBLISH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
