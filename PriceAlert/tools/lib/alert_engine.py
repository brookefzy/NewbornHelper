from __future__ import annotations


def categorize_alert(
    current_price: float,
    baseline_price: float | None,
    target_price: float | None,
    significant_drop_pct: float,
) -> tuple[str, float]:
    if baseline_price is None or baseline_price <= 0:
        drop_pct = 0.0
    else:
        drop_pct = round(((baseline_price - current_price) / baseline_price) * 100, 2)

    if drop_pct >= significant_drop_pct:
        return "SIGNIFICANT_DROP", drop_pct
    if target_price is not None and current_price <= target_price:
        return "TARGET_REACHED", drop_pct
    return "NO_ALERT", drop_pct
