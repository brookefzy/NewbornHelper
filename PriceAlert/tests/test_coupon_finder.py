from tools.lib.coupon_finder import find_signup_coupon


def test_coupon_finder_extracts_signup_offer_from_brand_page():
    html = "<html><body>Sign up and get 15% off your first order.</body></html>"
    result = find_signup_coupon("https://brand.example.com", fetch_html_fn=lambda _url: html)
    assert result is not None
    assert "15% off" in result["offer_text"]
