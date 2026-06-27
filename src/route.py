"""Alert routing — decide whether a scored catalyst emails you, batches, or just logs."""


def decide(rec, thresholds):
    score = rec.get("score", 0.0)
    investable = bool(rec.get("ticker")) or bool(rec.get("beneficiaries"))
    if not investable:
        rec["decision"] = "log"        # no tradable name -> dashboard only
        return rec["decision"]
    if score >= thresholds["immediate"]:
        rec["decision"] = "immediate"
    elif score >= thresholds["digest"]:
        rec["decision"] = "digest"
    else:
        rec["decision"] = "log"
    return rec["decision"]
