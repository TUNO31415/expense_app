from services.categorizer import categorize_row, choose_rule, match_rule


def test_longest_keyword_wins_before_priority():
    rules = [
        {"keyword": "shop", "category_id": 1, "action": "categorize", "priority": 100},
        {"keyword": "coffee shop", "category_id": 2, "action": "categorize", "priority": 0},
    ]
    assert choose_rule("Morning coffee shop", rules) == 2


def test_priority_breaks_ties_for_equal_length_keywords():
    rules = [
        {"keyword": "coffee", "category_id": 1, "action": "categorize", "priority": 1},
        {"keyword": "coffee", "category_id": 2, "action": "categorize", "priority": 5},
    ]
    assert choose_rule("Morning COFFEE beans", rules) == 2


def test_match_rule_reports_winning_ignore_rule():
    rules = [
        {"keyword": "transfer", "category_id": 9, "action": "categorize", "priority": 100},
        {"keyword": "savings", "category_id": None, "action": "ignore", "priority": 0},
    ]
    match = match_rule("Transfer to my savings account", rules)
    assert match is not None
    assert match.action == "ignore"
    assert categorize_row("Transfer to my savings account", rules, fallback_category_id=7) is None


def test_match_rule_returns_none_when_no_keyword_matches():
    assert match_rule("Bookstore", [{"keyword": "coffee", "category_id": 1}]) is None


def test_ignore_rule_drops_transaction():
    rules = [
        {"keyword": "savings", "category_id": None, "action": "ignore", "priority": 30},
        {"keyword": "transfer", "category_id": 9, "action": "categorize", "priority": 1},
    ]
    assert categorize_row("Transfer to my savings account", rules, fallback_category_id=7) is None
