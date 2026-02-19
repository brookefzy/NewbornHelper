from __future__ import annotations

from collections.abc import Callable


Collector = Callable[[dict], dict]


class PriceSourceRouter:
    def __init__(self, api_adapters: dict[str, Collector], scrape_collector: Collector):
        self.api_adapters = api_adapters
        self.scrape_collector = scrape_collector

    def fetch(self, product: dict) -> dict:
        platform = (product.get("platform") or "").lower()
        if platform in self.api_adapters:
            result = self.api_adapters[platform](product)
            result.setdefault("source_type", "api")
            return result

        result = self.scrape_collector(product)
        result.setdefault("source_type", "scrape")
        return result
