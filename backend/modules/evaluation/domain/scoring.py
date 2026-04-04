"""Pure score / label bucketing — no I/O."""

from __future__ import annotations


def quality_bucket_from_eval_label(label: str | None) -> str | None:
    """
    Map eval label strings into coarse quality buckets for rollups (insights, groups).

    Returns ``good`` | ``borderline`` | ``bad`` or None if unknown / empty.
    """
    if not label:
        return None
    l = label.lower()
    if l == "grounded":
        return "good"
    if l == "partially_grounded":
        return "borderline"
    if l == "not_grounded":
        return "bad"
    if l == "improved":
        return "good"
    if l == "unchanged":
        return "borderline"
    if l == "regressed":
        return "bad"
    return None


def count_bucket_totals(labels: list[str | None]) -> tuple[int, int, int]:
    good = borderline = bad = 0
    for lab in labels:
        b = quality_bucket_from_eval_label(lab)
        if b == "good":
            good += 1
        elif b == "borderline":
            borderline += 1
        elif b == "bad":
            bad += 1
    return good, borderline, bad
