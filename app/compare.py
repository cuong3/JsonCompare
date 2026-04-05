"""Pure comparison logic — no FastAPI imports."""

from collections import Counter, defaultdict
from statistics import mean, median

OUTPUT_FIELDS = (
    "side", "category", "subcategory", "tax_relevant",
    "tax_schedule", "confidence_score", "reasoning",
)
DEFAULT_KEY_FIELDS = ("description", "date", "amount")


def build_key(row: dict, key_fields: tuple[str, ...]) -> tuple:
    return tuple(row.get(f) for f in key_fields)


def pair_rows(
    left: list[dict],
    right: list[dict],
    key_fields: tuple[str, ...] = DEFAULT_KEY_FIELDS,
) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    """Return (matched, only_left, only_right).

    Duplicates sharing the same key are paired positionally within each group.
    """
    # Group right rows by key, preserving order within each key
    right_by_key: dict[tuple, list[dict]] = defaultdict(list)
    for row in right:
        right_by_key[build_key(row, key_fields)].append(row)

    matched: list[tuple[dict, dict]] = []
    only_left: list[dict] = []
    consumed: dict[tuple, int] = defaultdict(int)  # how many we've used per key

    for lrow in left:
        key = build_key(lrow, key_fields)
        idx = consumed[key]
        bucket = right_by_key.get(key, [])
        if idx < len(bucket):
            matched.append((lrow, bucket[idx]))
            consumed[key] += 1
        else:
            only_left.append(lrow)

    # Right rows that were never consumed
    only_right: list[dict] = []
    for key, bucket in right_by_key.items():
        start = consumed.get(key, 0)
        only_right.extend(bucket[start:])

    return matched, only_left, only_right


def diff_row(
    lrow: dict, rrow: dict, fields: tuple[str, ...] = OUTPUT_FIELDS
) -> dict[str, tuple]:
    """Return {field: (old_val, new_val)} for fields that differ."""
    diffs = {}
    for f in fields:
        lv = lrow.get(f)
        rv = rrow.get(f)
        if lv != rv:
            diffs[f] = (lv, rv)
    return diffs


def compute_stats(
    matched: list[tuple[dict, dict]],
    only_left: list[dict],
    only_right: list[dict],
    fields: tuple[str, ...] = OUTPUT_FIELDS,
) -> dict:
    changed_by_field: Counter = Counter()
    category_transitions: Counter = Counter()
    confidence_deltas: list[float] = []

    changed_rows = 0
    unchanged_rows = 0

    for lrow, rrow in matched:
        diffs = diff_row(lrow, rrow, fields)
        if diffs:
            changed_rows += 1
            for f in diffs:
                changed_by_field[f] += 1
            if "category" in diffs:
                old_cat, new_cat = diffs["category"]
                category_transitions[(old_cat, new_cat)] += 1
        else:
            unchanged_rows += 1

        # Confidence delta for every matched pair with numeric scores
        lc = lrow.get("confidence_score")
        rc = rrow.get("confidence_score")
        if isinstance(lc, (int, float)) and isinstance(rc, (int, float)):
            delta = rc - lc
            if delta != 0:
                confidence_deltas.append(delta)

    conf_stats = {}
    if confidence_deltas:
        conf_stats = {
            "mean": round(mean(confidence_deltas), 4),
            "median": round(median(confidence_deltas), 4),
            "min": round(min(confidence_deltas), 4),
            "max": round(max(confidence_deltas), 4),
            "n": len(confidence_deltas),
        }

    return {
        "total_left": len(only_left) + len(matched),
        "total_right": len(only_right) + len(matched),
        "matched": len(matched),
        "added": len(only_right),
        "removed": len(only_left),
        "changed": changed_rows,
        "unchanged": unchanged_rows,
        "changed_by_field": dict(changed_by_field.most_common()),
        "category_transitions": {
            f"{old} -> {new}": count
            for (old, new), count in category_transitions.most_common()
        },
        "confidence_delta": conf_stats,
    }


def compare_files(
    left: list[dict],
    right: list[dict],
    key_fields: tuple[str, ...] = DEFAULT_KEY_FIELDS,
    output_fields: tuple[str, ...] = OUTPUT_FIELDS,
) -> dict:
    """High-level entry point. Returns everything the template needs."""
    matched, only_left, only_right = pair_rows(left, right, key_fields)

    rows = []
    for lrow, rrow in matched:
        diffs = diff_row(lrow, rrow, output_fields)
        rows.append({
            "type": "matched",
            "left": lrow,
            "right": rrow,
            "diffs": diffs,
            "changed": bool(diffs),
        })
    for row in only_left:
        rows.append({"type": "removed", "left": row, "right": None, "diffs": {}, "changed": True})
    for row in only_right:
        rows.append({"type": "added", "left": None, "right": row, "diffs": {}, "changed": True})

    stats = compute_stats(matched, only_left, only_right, output_fields)

    return {"rows": rows, "stats": stats, "key_fields": list(key_fields), "output_fields": list(output_fields)}
