from tools.lib.url_validator import validate_candidate_url


def test_validate_candidate_url_accepts_strong_pdp_match():
    result = validate_candidate_url(
        url="https://www.target.com/p/hudson-convertible-crib/-/A-12345678",
        platform="target",
        product={"brand": "Babyletto", "product_name": "Hudson Convertible Crib"},
        candidate_title="Babyletto Hudson Convertible Crib",
        candidate_snippet="Convertible crib from Babyletto collection",
    )
    assert result["is_useful"] is True
    assert result["allowed_domain"] is True
    assert result["path_relevant"] is True
    assert result["keyword_overlap"] >= 2


def test_validate_candidate_url_rejects_off_domain():
    result = validate_candidate_url(
        url="https://www.example.com/p/hudson-convertible-crib",
        platform="target",
        product={"brand": "Babyletto", "product_name": "Hudson Convertible Crib"},
        candidate_title="Babyletto Hudson Convertible Crib",
        candidate_snippet="Convertible crib",
    )
    assert result["is_useful"] is False
    assert result["allowed_domain"] is False


def test_validate_candidate_url_rejects_low_keyword_overlap():
    result = validate_candidate_url(
        url="https://www.target.com/p/metal-lamp/-/A-11111111",
        platform="target",
        product={"brand": "Babyletto", "product_name": "Hudson Convertible Crib"},
        candidate_title="Modern Metal Lamp",
        candidate_snippet="home decor lighting",
    )
    assert result["is_useful"] is False
    assert result["keyword_overlap"] < 2


def test_validate_candidate_url_rejects_irrelevant_path():
    result = validate_candidate_url(
        url="https://www.target.com/s?searchTerm=hudson+crib",
        platform="target",
        product={"brand": "Babyletto", "product_name": "Hudson Convertible Crib"},
        candidate_title="Babyletto Hudson Convertible Crib",
        candidate_snippet="Shop all cribs",
    )
    assert result["is_useful"] is False
    assert result["path_relevant"] is False
