"""Catalyst scoring model (0-10 descriptive triage scale).

score = quality_weight x stage_mult x materiality_mult x derisk x dissemination, scaled.
The surprise/expectedness factor is intentionally dropped in v1 to keep scoring
deterministic. The score ranks what's worth your attention; it does not predict the move.
"""

QUALITY_WEIGHT = {1: 1.0, 2: 0.8, 3: 0.55, 4: 0.35, 5: 0.15}
STAGE_MULT = {1: 0.4, 2: 0.6, 3: 0.7, 4: 1.0, 5: 1.2, 6: 0.8}
SCALE = 3.2


def materiality_mult(ratio):
    if ratio is None:
        return 0.5          # unknown amount/cap -> neutral-low
    if ratio > 0.25:
        return 2.0          # transformative
    if ratio >= 0.10:
        return 1.5
    if ratio >= 0.03:
        return 1.0
    if ratio >= 0.01:
        return 0.6
    return 0.2              # rounding error (large-cap grant)


def score_record(rec):
    tier = rec.get("quality_tier") or 4
    stage = rec.get("stage") or 4
    qw = QUALITY_WEIGHT.get(tier, 0.35)
    sm = STAGE_MULT.get(stage, 1.0)
    mm = materiality_mult(rec.get("materiality_ratio"))
    derisk = 1.3 if (rec.get("tier1_hit") or rec.get("amount_type") == "offtake") else 1.0
    dissem = 1.0 if rec.get("dissemination", "primary") == "primary" else 0.4
    raw = qw * sm * mm * derisk * dissem
    rec["score"] = round(raw * SCALE, 1)
    return rec["score"]
