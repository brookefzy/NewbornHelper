from unittest.mock import Mock

from tools.lib.openai_web_search import _build_candidate_ranking_prompt
from tools.lib.openai_web_search import search_product_candidates_with_openai


def test_search_product_candidates_with_openai_normalizes_schema():
    request_fn = Mock(
        return_value={
            "output_text": '[{"candidate_url":"https://www.target.com/p/widget/-/A-12345","title":"Widget","snippet":"Great widget","domain":"target.com","match_score":0.87}]'
        }
    )

    rows = search_product_candidates_with_openai(
        product={
            "product_name": "Widget",
            "brand": "Acme",
            "product_id": "p1",
        },
        platform="target",
        api_key="sk-test",
        request_fn=request_fn,
    )

    assert rows == [
        {
            "candidate_url": "https://www.target.com/p/widget/-/A-12345",
            "title": "Widget",
            "snippet": "Great widget",
            "domain": "target.com",
            "match_score": 0.87,
            "rank": 1,
            "query": "Acme Widget target",
            "reason": "openai_web_search",
        }
    ]


def test_search_product_candidates_with_openai_retries_then_succeeds():
    request_fn = Mock(
        side_effect=[
            RuntimeError("timeout"),
            {"output_text": "[]"},
        ]
    )

    rows = search_product_candidates_with_openai(
        product={"product_name": "Crib", "brand": "Babyletto", "product_id": "p2"},
        platform="babyletto",
        api_key="sk-test",
        max_retries=2,
        request_fn=request_fn,
    )

    assert rows == []
    assert request_fn.call_count == 2


def test_build_candidate_ranking_prompt_requires_brand_and_product_terms():
    prompt = _build_candidate_ranking_prompt(product_name="Pogo Stroller", brand="UppaBaby", platform="target")
    lowered = prompt.lower()
    assert "uppababy" in lowered
    assert "pogo stroller" in lowered
    assert "target" in lowered
