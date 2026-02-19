from tools.lib.source_router import PriceSourceRouter


def test_source_router_prefers_api_or_feed_before_scraping():
    def api_adapter(_product):
        return {"status": "ok", "current_price": 199.0, "source_type": "api"}

    def scraper(_product):
        return {"status": "ok", "current_price": 209.0, "source_type": "scrape"}

    router = PriceSourceRouter(api_adapters={"amazon": api_adapter}, scrape_collector=scraper)
    result = router.fetch({"product_id": "p1", "platform": "amazon", "product_url": "https://example.com"})

    assert result["source_type"] == "api"
    assert result["current_price"] == 199.0
