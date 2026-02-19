from tools.lib.email_renderer import render_digest_html


def test_email_html_prioritizes_top_drops_and_coupon_section():
    html = render_digest_html(
        run_date="2026-02-18",
        top_drops=[{"product_name": "Stroller", "current_price": 399.0, "drop_pct": 20.0}],
        all_items=[{"product_name": "Stroller", "current_price": 399.0, "baseline_price": 499.0, "target_price": 420.0}],
        coupons=[{"brand": "BrandA", "offer_text": "Sign up and get 15% off", "source_url": "https://brand.example.com"}],
    )

    assert "Top Significant Drops" in html
    assert "Coupon Opportunities" in html
    assert "Stroller" in html
    assert "15% off" in html
