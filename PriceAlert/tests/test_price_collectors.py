from tools.lib.price_collectors import collect_price, has_snippet_price_signal


def test_extract_price_from_supported_platform_html():
    html = """
    <html><body>
      <span class="a-price-whole">199</span><span class="a-price-fraction">99</span>
    </body></html>
    """

    result = collect_price(
        {"product_id": "p1", "platform": "amazon", "product_url": "https://example.com/item"},
        fetch_html_fn=lambda _url: html,
    )

    assert result["status"] == "ok"
    assert result["current_price"] == 199.99
    assert result["currency"] == "USD"


def test_has_snippet_price_signal_detects_currency_pattern():
    assert has_snippet_price_signal("Now only $479.99 at Target") is True
    assert has_snippet_price_signal("See product details and reviews") is False
