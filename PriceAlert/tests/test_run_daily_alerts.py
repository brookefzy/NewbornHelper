import json
from pathlib import Path

from tools.run_daily_price_alerts import _apply_approved_urls, _resolve_source_url, run_daily_pipeline


def test_daily_runner_executes_pipeline_and_sends_single_digest(tmp_path: Path):
    products = [
        {
            "product_id": "p1",
            "product_name": "Stroller",
            "brand": "BrandA",
            "platform": "amazon",
            "product_url": "",
            "baseline_price": 100.0,
            "target_price": 90.0,
            "significant_drop_pct": 10.0,
        }
    ]

    sent = []
    history_rows = []
    output_path = tmp_path / "latest_run.json"

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda p, html=None: {"status": "ok", "current_price": 80.0, "currency": "USD"},
        coupon_fetcher=lambda _url, html=None: {"offer_text": "Sign up and get 15% off", "source_url": "https://brand.example.com"},
        discover_candidates_fn=lambda _p, _platform: [{"candidate_url": "https://www.amazon.com/dp/B000TEST01", "query": "q", "rank": 1, "reason": "domain_match"}],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "ok", "path": str(output_path)},
        llm_fallback_fn=None,
        digest_sender=lambda payload: sent.append(payload),
        history_writer=lambda rows: history_rows.extend(rows),
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
    )

    assert summary["processed"] == 1
    assert summary["alerts"] == 0
    assert len(sent) == 1
    assert len(history_rows) == 1
    assert sent[0]["all_items"] == []
    assert summary["items"][0]["status"] == "no_data"
    assert summary["items"][0]["error"] == "platform_not_supported"
    assert summary["items"][0]["snapshot_status"] == "skip"
    assert summary["openai_fallback_attempts"] == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["processed"] == 1


def test_apply_approved_urls_overrides_nonapproved_platforms():
    records = [
        {"product_id": "1", "platform": "target", "product_url": "https://old.example.com/target"},
        {"product_id": "1", "platform": "amazon", "product_url": "https://old.example.com/amazon"},
    ]
    approved = {("1", "target"): "https://www.target.com/p/hudson/-/A-12345678"}

    _apply_approved_urls(records, approved)

    assert records[0]["product_url"] == "https://www.target.com/p/hudson/-/A-12345678"
    assert records[1]["product_url"] == "https://old.example.com/amazon"


def test_resolve_source_url_precedence():
    assert (
        _resolve_source_url(
            approved_url="https://approved.example.com/pdp",
            discovered_url="https://discovered.example.com/pdp",
            fallback_url="https://fallback.example.com/pdp",
        )
        == "https://approved.example.com/pdp"
    )
    assert (
        _resolve_source_url(
            approved_url="",
            discovered_url="https://discovered.example.com/pdp",
            fallback_url="https://fallback.example.com/pdp",
        )
        == "https://discovered.example.com/pdp"
    )
    assert (
        _resolve_source_url(
            approved_url="",
            discovered_url="",
            fallback_url="https://fallback.example.com/pdp",
        )
        == "https://fallback.example.com/pdp"
    )


def test_daily_runner_does_not_alert_when_price_missing(tmp_path: Path):
    products = [
        {
            "product_id": "p2",
            "product_name": "Crib",
            "brand": "BrandB",
            "platform": "target",
            "product_url": "https://www.target.com/p/example",
            "baseline_price": 500.0,
            "target_price": 450.0,
            "significant_drop_pct": 10.0,
        }
    ]

    sent = []
    history_rows = []
    output_path = tmp_path / "latest_run.json"

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda _p, html=None: {"status": "fetch_error", "current_price": None, "currency": "USD"},
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "ok", "path": str(output_path)},
        llm_fallback_fn=None,
        digest_sender=lambda payload: sent.append(payload),
        history_writer=lambda rows: history_rows.extend(rows),
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
    )

    assert summary["alerts"] == 0
    assert sent[0]["all_items"] == []
    assert summary["best_items"] == []
    assert summary["openai_fallback_attempts"] == 0


def test_daily_runner_uses_openai_fallback_for_low_confidence(tmp_path: Path):
    products = [
        {
            "product_id": "p3",
            "product_name": "Mattress",
            "brand": "BrandC",
            "platform": "babyletto",
            "product_url": "https://babyletto.com/products/example",
            "baseline_price": 300.0,
            "target_price": 280.0,
            "significant_drop_pct": 10.0,
        }
    ]
    sent = []
    output_path = tmp_path / "latest_run.json"
    html_path = tmp_path / "page.html"
    html_path.write_text("<html>$300.00</html>", encoding="utf-8")

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda _p, html=None: {"status": "ok", "current_price": 299.0, "currency": "USD", "confidence": 0.2},
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "ok", "path": str(html_path)},
        llm_fallback_fn=lambda **kwargs: {"status": "ok", "current_price": 250.0, "currency": "USD", "confidence": 0.9},
        digest_sender=lambda payload: sent.append(payload),
        history_writer=lambda rows: None,
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
        max_openai_fallbacks=1,
    )

    assert summary["openai_fallback_uses"] == 1
    assert summary["openai_fallback_attempts"] == 1
    assert sent[0]["all_items"][0]["current_price"] == 250.0


def test_daily_runner_uses_search_url_candidates_as_last_resort(tmp_path: Path):
    products = [
        {
            "product_id": "p4",
            "product_name": "Stroller",
            "brand": "BrandD",
            "platform": "amazon",
            "product_url": "",
            "baseline_price": 500.0,
            "target_price": 450.0,
            "significant_drop_pct": 10.0,
        }
    ]
    sent = []
    output_path = tmp_path / "latest_run.json"

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda _p, html=None: {"status": "ok", "current_price": 400.0, "currency": "USD", "confidence": 0.9},
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [{"candidate_url": "https://www.amazon.com/s?k=stroller", "query": "q", "rank": 1, "reason": "search"}],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "ok", "path": str(output_path)},
        llm_fallback_fn=None,
        digest_sender=lambda payload: sent.append(payload),
        history_writer=lambda rows: None,
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
    )

    assert summary["unresolved_urls"] == 1
    assert summary["items"][0]["product_url"] == ""
    assert summary["items"][0]["status"] == "no_data"
    assert summary["items"][0]["error"] == "platform_not_supported"
    assert sent[0]["all_items"] == []


def test_daily_runner_prefers_candidate_with_product_path_over_homepage(tmp_path: Path):
    products = [
        {
            "product_id": "p5",
            "product_name": "Hudson Convertible Crib",
            "brand": "Babyletto",
            "platform": "babyletto",
            "product_url": "",
            "baseline_price": 499.0,
            "target_price": 399.0,
            "significant_drop_pct": 10.0,
        }
    ]
    sent = []
    output_path = tmp_path / "latest_run.json"
    html_path = tmp_path / "page.html"
    html_path.write_text("<html>$499.00</html>", encoding="utf-8")

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda _p, html=None: {"status": "ok", "current_price": 499.0, "currency": "USD", "confidence": 0.9},
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [
            {"candidate_url": "https://babyletto.com", "query": "q1", "rank": 1, "reason": "domain"},
            {"candidate_url": "https://babyletto.com/products/hudson-convertible-crib", "query": "q1", "rank": 2, "reason": "domain"},
        ],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "ok", "path": str(html_path)},
        llm_fallback_fn=None,
        digest_sender=lambda payload: sent.append(payload),
        history_writer=lambda rows: None,
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
    )

    assert summary["unresolved_urls"] == 0
    assert sent[0]["all_items"][0]["product_url"] == "https://babyletto.com/products/hudson-convertible-crib"


def test_daily_runner_prefers_validated_pdp_candidate(tmp_path: Path):
    products = [
        {
            "product_id": "p5b",
            "product_name": "Hudson Convertible Crib",
            "brand": "Babyletto",
            "platform": "target",
            "product_url": "",
            "baseline_price": 499.0,
            "target_price": 399.0,
            "significant_drop_pct": 10.0,
        }
    ]
    sent = []
    output_path = tmp_path / "latest_run.json"
    pdp_html = tmp_path / "target-pdp.html"
    pdp_html.write_text("<html>Babyletto Hudson Convertible Crib $479.99</html>", encoding="utf-8")

    def snapshot(url, _product_id, _platform):
        if "/p/" in url:
            return {"status": "ok", "path": str(pdp_html)}
        return {"status": "ok", "path": str(output_path)}

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda _p, html=None: {"status": "ok", "current_price": 479.99, "currency": "USD", "confidence": 0.9},
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [
            {"candidate_url": "https://www.target.com/s?searchTerm=crib", "query": "q1", "rank": 1, "reason": "search"},
            {"candidate_url": "https://www.target.com/p/hudson-convertible-crib/-/A-12345678", "query": "q1", "rank": 2, "reason": "domain_match"},
        ],
        snapshot_fn=snapshot,
        llm_fallback_fn=None,
        digest_sender=lambda payload: sent.append(payload),
        history_writer=lambda rows: None,
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
    )

    assert summary["unresolved_urls"] == 0
    assert sent[0]["all_items"][0]["product_url"] == "https://www.target.com/p/hudson-convertible-crib/-/A-12345678"


def test_daily_runner_alerts_use_lowest_price_across_platforms(tmp_path: Path):
    products = [
        {
            "product_id": "p6",
            "product_name": "Travel System",
            "brand": "BrandZ",
            "platform": "target",
            "product_url": "https://target.com/p/example",
            "baseline_price": 900.0,
            "target_price": 850.0,
            "significant_drop_pct": 5.0,
        },
        {
            "product_id": "p6",
            "product_name": "Travel System",
            "brand": "BrandZ",
            "platform": "nordstrom",
            "product_url": "https://nordstrom.com/s/example",
            "baseline_price": 900.0,
            "target_price": 850.0,
            "significant_drop_pct": 5.0,
        },
    ]
    sent = []
    best_rows = []
    output_path = tmp_path / "latest_run.json"
    html_path = tmp_path / "page.html"
    html_path.write_text("<html>$799</html>", encoding="utf-8")

    def fetcher(product, html=None):
        if product["platform"] == "target":
            return {"status": "ok", "current_price": 840.0, "currency": "USD", "confidence": 0.9}
        return {"status": "ok", "current_price": 799.0, "currency": "USD", "confidence": 0.9}

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=fetcher,
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "ok", "path": str(html_path)},
        llm_fallback_fn=None,
        digest_sender=lambda payload: sent.append(payload),
        history_writer=lambda rows: None,
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: best_rows.extend(rows),
        output_json_path=output_path,
    )

    assert summary["alerts"] == 1
    assert len(sent[0]["top_drops"]) == 1
    assert sent[0]["top_drops"][0]["current_price"] == 799.0
    assert len(sent[0]["all_items"]) == 1
    assert sent[0]["all_items"][0]["platform"] == "nordstrom"
    assert len(best_rows) == 1


def test_daily_runner_rejects_target_homepage_without_pdp_pattern(tmp_path: Path):
    products = [
        {
            "product_id": "p7",
            "product_name": "Crib",
            "brand": "BrandT",
            "platform": "target",
            "product_url": "",
            "baseline_price": 500.0,
            "target_price": 450.0,
            "significant_drop_pct": 10.0,
        }
    ]
    sent = []
    output_path = tmp_path / "latest_run.json"

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda _p, html=None: {"status": "ok", "current_price": 400.0, "currency": "USD", "confidence": 0.9},
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [{"candidate_url": "https://target.com", "query": "q", "rank": 1, "reason": "domain_match"}],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "ok", "path": str(output_path)},
        llm_fallback_fn=None,
        digest_sender=lambda payload: sent.append(payload),
        history_writer=lambda rows: None,
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
    )

    assert summary["unresolved_urls"] == 1
    assert summary["items"][0]["product_url"] == ""
    assert summary["items"][0]["status"] == "no_url"


def test_daily_runner_accepts_target_pdp_pattern(tmp_path: Path):
    products = [
        {
            "product_id": "p8",
            "product_name": "Crib",
            "brand": "BrandT",
            "platform": "target",
            "product_url": "",
            "baseline_price": 500.0,
            "target_price": 450.0,
            "significant_drop_pct": 10.0,
        }
    ]
    sent = []
    output_path = tmp_path / "latest_run.json"
    html_path = tmp_path / "page.html"
    html_path.write_text("<html>$460.00</html>", encoding="utf-8")

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda _p, html=None: {"status": "ok", "current_price": 460.0, "currency": "USD", "confidence": 0.9},
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [
            {
                "candidate_url": "https://www.target.com/p/example-crib/-/A-12345678",
                "query": "q",
                "rank": 1,
                "reason": "domain_match",
            }
        ],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "ok", "path": str(html_path)},
        llm_fallback_fn=None,
        digest_sender=lambda payload: sent.append(payload),
        history_writer=lambda rows: None,
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
    )

    assert summary["unresolved_urls"] == 0
    assert summary["best_items"][0]["product_url"] == "https://www.target.com/p/example-crib/-/A-12345678"


def test_daily_runner_falls_back_to_target_search_url_when_no_pdp(tmp_path: Path):
    products = [
        {
            "product_id": "p9",
            "product_name": "Crib",
            "brand": "BrandT",
            "platform": "target",
            "product_url": "",
            "baseline_price": 500.0,
            "target_price": 450.0,
            "significant_drop_pct": 10.0,
        }
    ]
    output_path = tmp_path / "latest_run.json"
    html_path = tmp_path / "search.html"
    html_path.write_text("<html>$470.00</html>", encoding="utf-8")

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda _p, html=None: {"status": "ok", "current_price": 470.0, "currency": "USD", "confidence": 0.8},
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [
            {
                "candidate_url": "https://www.target.com/s?searchTerm=crib",
                "query": "q",
                "rank": 1,
                "reason": "heuristic_platform_search",
            }
        ],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "ok", "path": str(html_path)},
        llm_fallback_fn=None,
        digest_sender=lambda payload: None,
        history_writer=lambda rows: None,
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
    )

    assert summary["unresolved_urls"] == 0
    assert summary["items"][0]["product_url"] == "https://www.target.com/s?searchTerm=crib"


def test_daily_runner_rejects_listing_price_even_when_llm_fallback_returns_price(tmp_path: Path):
    products = [
        {
            "product_id": "p10",
            "product_name": "Waterproof Crib Mattress",
            "brand": "Newtonbaby",
            "platform": "nordstrom",
            "product_url": "",
            "baseline_price": 349.99,
            "target_price": 300.0,
            "significant_drop_pct": 20.0,
        }
    ]
    output_path = tmp_path / "latest_run.json"
    html_path = tmp_path / "listing.html"
    html_path.write_text("<html>listing page</html>", encoding="utf-8")

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda _p, html=None: {
            "status": "parse_error",
            "current_price": None,
            "currency": "USD",
            "confidence": 0.0,
            "error": "price_not_found",
        },
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [
            {
                "candidate_url": "https://www.nordstrom.com/sr?keyword=Newtonbaby+Waterproof+Crib+Mattress",
                "query": "q",
                "rank": 1,
                "reason": "heuristic_platform_search",
            }
        ],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "ok", "path": str(html_path)},
        llm_fallback_fn=lambda **_kwargs: {
            "status": "ok",
            "current_price": 149.99,
            "currency": "USD",
            "confidence": 0.9,
            "error": None,
        },
        digest_sender=lambda payload: None,
        history_writer=lambda rows: None,
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
        max_openai_fallbacks=5,
    )

    assert summary["items"][0]["status"] == "parse_error"
    assert summary["items"][0]["error"] in {"listing_page_price_untrusted", "price_not_found"}
    assert summary["openai_fallback_attempts"] == 0
    assert summary["items"][0]["current_price"] is None


def test_hybrid_retailer_flow_search_fetch_parse_success(tmp_path: Path):
    products = [
        {
            "product_id": "p11",
            "product_name": "Hudson Convertible Crib",
            "brand": "Babyletto",
            "platform": "target",
            "product_url": "",
            "baseline_price": 499.0,
            "target_price": 450.0,
            "significant_drop_pct": 10.0,
        }
    ]
    html_path = tmp_path / "target-pdp.html"
    html_path.write_text("<html>Babyletto Hudson Convertible Crib $479.99</html>", encoding="utf-8")
    output_path = tmp_path / "latest_run.json"

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda _p, html=None: {
            "status": "ok",
            "current_price": 479.99,
            "currency": "USD",
            "confidence": 0.95,
            "error": None,
        },
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [
            {
                "candidate_url": "https://www.target.com/p/hudson-convertible-crib/-/A-12345678",
                "query": "q",
                "rank": 1,
                "reason": "openai_web_search",
                "snippet": "Hudson Convertible Crib $479.99",
            }
        ],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "ok", "path": str(html_path)},
        llm_fallback_fn=None,
        retailer_parse_fn=None,
        digest_sender=lambda payload: None,
        history_writer=lambda rows: None,
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
    )

    assert summary["items"][0]["status"] == "ok"
    assert summary["items"][0]["current_price"] == 479.99


def test_hybrid_retailer_snippet_price_unverified_when_html_parse_fails(tmp_path: Path):
    products = [
        {
            "product_id": "p12",
            "product_name": "Hudson Convertible Crib",
            "brand": "Babyletto",
            "platform": "target",
            "product_url": "",
            "baseline_price": 499.0,
            "target_price": 450.0,
            "significant_drop_pct": 10.0,
        }
    ]
    html_path = tmp_path / "target-pdp.html"
    html_path.write_text("<html>No price here</html>", encoding="utf-8")
    output_path = tmp_path / "latest_run.json"

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda _p, html=None: {
            "status": "parse_error",
            "current_price": None,
            "currency": "USD",
            "confidence": 0.0,
            "error": "price_not_found",
        },
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [
            {
                "candidate_url": "https://www.target.com/p/hudson-convertible-crib/-/A-12345678",
                "query": "q",
                "rank": 1,
                "reason": "openai_web_search",
                "snippet": "Hudson Convertible Crib now $479.99",
            }
        ],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "ok", "path": str(html_path)},
        llm_fallback_fn=None,
        retailer_parse_fn=lambda **_kwargs: None,
        digest_sender=lambda payload: None,
        history_writer=lambda rows: None,
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
    )

    assert summary["items"][0]["status"] == "parse_error"
    assert summary["items"][0]["error"] == "search_price_unverified"


def test_search_budget_exhaustion_does_not_consume_parse_budget(tmp_path: Path):
    products = [
        {
            "product_id": "p13",
            "product_name": "Crib",
            "brand": "Babyletto",
            "platform": "target",
            "product_url": "",
            "baseline_price": 500.0,
            "target_price": 450.0,
            "significant_drop_pct": 10.0,
        }
    ]
    output_path = tmp_path / "latest_run.json"
    parse_calls = []

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda _p, html=None: {"status": "parse_error", "current_price": None, "currency": "USD", "confidence": 0.0},
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [{"candidate_url": "https://www.target.com/p/example/-/A-123", "query": "q", "rank": 1, "reason": "openai_web_search"}],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "skip"},
        llm_fallback_fn=lambda **_kwargs: {"status": "ok", "current_price": 400.0, "currency": "USD", "confidence": 0.9},
        retailer_parse_fn=lambda **_kwargs: parse_calls.append(1) or None,
        digest_sender=lambda payload: None,
        history_writer=lambda rows: None,
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
        max_openai_search_calls=0,
        max_openai_retailer_parse_calls=5,
    )

    assert summary["openai_search_attempts"] == 0
    assert summary["openai_search_uses"] == 0
    assert summary["openai_retailer_parse_attempts"] == 0
    assert parse_calls == []


def test_retailer_parse_budget_exhaustion_does_not_consume_fallback_budget(tmp_path: Path):
    products = [
        {
            "product_id": "p14",
            "product_name": "Crib",
            "brand": "Babyletto",
            "platform": "target",
            "product_url": "https://www.target.com/p/example-crib/-/A-12345678",
            "baseline_price": 500.0,
            "target_price": 450.0,
            "significant_drop_pct": 10.0,
        }
    ]
    output_path = tmp_path / "latest_run.json"
    html_path = tmp_path / "page.html"
    html_path.write_text("<html>No price</html>", encoding="utf-8")

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda _p, html=None: {"status": "parse_error", "current_price": None, "currency": "USD", "confidence": 0.0, "error": "price_not_found"},
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "ok", "path": str(html_path)},
        llm_fallback_fn=lambda **_kwargs: {"status": "ok", "current_price": 399.0, "currency": "USD", "confidence": 0.9},
        retailer_parse_fn=lambda **_kwargs: {"status": "ok", "current_price": 389.0, "currency": "USD", "confidence": 0.9},
        digest_sender=lambda payload: None,
        history_writer=lambda rows: None,
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
        max_openai_retailer_parse_calls=0,
        max_openai_fallbacks=5,
    )

    assert summary["openai_retailer_parse_attempts"] == 0
    assert summary["openai_fallback_attempts"] == 0
    assert summary["openai_fallback_uses"] == 0


def test_fallback_budget_applies_only_to_deterministic_path(tmp_path: Path):
    products = [
        {
            "product_id": "p15a",
            "product_name": "Hudson Convertible Crib",
            "brand": "Babyletto",
            "platform": "babyletto",
            "product_url": "https://babyletto.com/products/hudson-crib",
            "baseline_price": 500.0,
            "target_price": 450.0,
            "significant_drop_pct": 10.0,
        },
        {
            "product_id": "p15b",
            "product_name": "Hudson Convertible Crib",
            "brand": "Babyletto",
            "platform": "target",
            "product_url": "https://www.target.com/p/hudson-convertible-crib/-/A-12345678",
            "baseline_price": 500.0,
            "target_price": 450.0,
            "significant_drop_pct": 10.0,
        },
    ]
    output_path = tmp_path / "latest_run.json"
    html_path = tmp_path / "page.html"
    html_path.write_text("<html>No price</html>", encoding="utf-8")

    summary = run_daily_pipeline(
        products=products,
        price_fetcher=lambda product, html=None: {
            "status": "parse_error",
            "current_price": None,
            "currency": "USD",
            "confidence": 0.0,
            "error": f"price_not_found_{product['platform']}",
        },
        coupon_fetcher=lambda _url, html=None: None,
        discover_candidates_fn=lambda _p, _platform: [],
        snapshot_fn=lambda _url, _product_id, _platform: {"status": "ok", "path": str(html_path)},
        llm_fallback_fn=lambda **_kwargs: {"status": "ok", "current_price": 410.0, "currency": "USD", "confidence": 0.9},
        retailer_parse_fn=lambda **_kwargs: None,
        digest_sender=lambda payload: None,
        history_writer=lambda rows: None,
        url_candidate_writer=lambda rows: None,
        best_price_writer=lambda rows: None,
        output_json_path=output_path,
        max_openai_fallbacks=1,
        max_openai_retailer_parse_calls=0,
    )

    assert summary["openai_fallback_attempts"] == 1
    assert summary["openai_fallback_uses"] == 1
