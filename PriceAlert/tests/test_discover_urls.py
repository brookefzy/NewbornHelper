from tools.discover_urls import _choose_selected_candidate


def test_choose_selected_candidate_uses_highest_validation_score():
    candidates = [
        {"candidate_url": "https://example.com/a", "rank": 1},
        {"candidate_url": "https://example.com/b", "rank": 2},
    ]
    validations = {
        "https://example.com/a": {"score": 2},
        "https://example.com/b": {"score": 9},
    }
    selected = _choose_selected_candidate(candidates, validations)
    assert selected == "https://example.com/b"


def test_choose_selected_candidate_breaks_tie_by_rank():
    candidates = [
        {"candidate_url": "https://example.com/a", "rank": 1},
        {"candidate_url": "https://example.com/b", "rank": 2},
    ]
    validations = {
        "https://example.com/a": {"score": 5},
        "https://example.com/b": {"score": 5},
    }
    selected = _choose_selected_candidate(candidates, validations)
    assert selected == "https://example.com/a"

