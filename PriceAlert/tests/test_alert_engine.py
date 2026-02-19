from tools.lib.alert_engine import categorize_alert


def test_alert_engine_flags_significant_drop_and_target_hit():
    category, drop_pct = categorize_alert(
        current_price=80.0,
        baseline_price=100.0,
        target_price=90.0,
        significant_drop_pct=10.0,
    )
    assert category == "SIGNIFICANT_DROP"
    assert drop_pct == 20.0
