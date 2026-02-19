from tools.lib.platform_strategy import unsupported_platform_result
from tools.lib.platform_strategy import resolve_extraction_strategy


def test_resolve_extraction_strategy_maps_known_platforms():
    assert resolve_extraction_strategy("babyletto") == "deterministic"
    assert resolve_extraction_strategy("newtonbaby") == "deterministic"
    assert resolve_extraction_strategy("target") == "hybrid_retailer"
    assert resolve_extraction_strategy("nordstrom") == "hybrid_retailer"


def test_resolve_extraction_strategy_falls_back_to_unsupported():
    assert resolve_extraction_strategy("amazon") == "unsupported"
    assert resolve_extraction_strategy("unknown") == "unsupported"


def test_unsupported_platform_result_shape():
    result = unsupported_platform_result(platform="amazon")
    assert result["status"] == "no_data"
    assert result["error"] == "platform_not_supported"
    assert result["snapshot_status"] == "skip"
    assert result["platform"] == "amazon"

