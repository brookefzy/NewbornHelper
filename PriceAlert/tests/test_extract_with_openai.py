from tools.lib.extract_with_openai import extract_price_and_coupon_with_openai


def test_openai_fallback_parses_structured_response():
    def fake_request(_payload, _api_key):
        return {
            "output_text": (
                '{"price": 299.99, "currency": "USD", "coupon_text": "Sign up for 10% off", '
                '"confidence": 0.74, "evidence_text": "$299.99"}'
            )
        }

    result = extract_price_and_coupon_with_openai(
        html="<html>$299.99</html>",
        url="https://example.com",
        api_key="sk-test",
        request_fn=fake_request,
    )
    assert result is not None
    assert result["status"] == "ok"
    assert result["current_price"] == 299.99
    assert result["coupon_text"] == "Sign up for 10% off"


def test_openai_fallback_parses_responses_output_content_shape():
    def fake_request(_payload, _api_key):
        return {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"price": 410.0, "currency": "USD", "coupon_text": null, "confidence": 0.81, "evidence_text": "$410.00"}',
                        }
                    ]
                }
            ]
        }

    result = extract_price_and_coupon_with_openai(
        html="<html>$410.00</html>",
        url="https://example.com/p",
        api_key="sk-test",
        request_fn=fake_request,
    )
    assert result is not None
    assert result["status"] == "ok"
    assert result["current_price"] == 410.0


def test_openai_parse_supports_custom_source_label():
    def fake_request(_payload, _api_key):
        return {
            "output_text": '{"price": 389.0, "currency": "USD", "coupon_text": null, "confidence": 0.88, "evidence_text": "$389.00"}'
        }

    result = extract_price_and_coupon_with_openai(
        html="<html>$389.00</html>",
        url="https://example.com/p",
        api_key="sk-test",
        request_fn=fake_request,
        source_label="openai_retailer_parse",
    )
    assert result is not None
    assert result["source"] == "openai_retailer_parse"
