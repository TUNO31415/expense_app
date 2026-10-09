from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class RuleMatch:
    action: str
    keyword: str
    priority: int
    category_id: int | None = None


def match_rule(description: str, rules: Iterable[dict[str, Any]]) -> RuleMatch | None:
    """Return the winning rule: ignore wins, then keyword length, then priority."""
    normalized = (description or "").casefold()
    matching_ignores: list[RuleMatch] = []
    matching_categories: list[RuleMatch] = []

    for rule in rules:
        keyword = str(rule.get("keyword") or "").strip().casefold()
        if not keyword or keyword not in normalized:
            continue

        action = str(rule.get("action") or "categorize")
        category_id = rule.get("category_id")
        match = RuleMatch(
            action=action,
            keyword=keyword,
            priority=int(rule.get("priority", 0)),
            category_id=int(category_id) if category_id is not None else None,
        )
        if action == "ignore":
            matching_ignores.append(match)
        elif match.category_id is not None:
            matching_categories.append(match)

    if matching_ignores:
        return max(matching_ignores, key=lambda item: (len(item.keyword), item.priority))
    if matching_categories:
        return max(matching_categories, key=lambda item: (len(item.keyword), item.priority))
    return None


def choose_rule(description: str, rules: Iterable[dict[str, Any]]) -> int | None:
    """Pick the winning non-ignore rule by longest match and then priority."""
    category_rules = (rule for rule in rules if str(rule.get("action") or "categorize") != "ignore")
    match = match_rule(description, category_rules)
    return match.category_id if match is not None else None


def categorize_row(description: str, rules: Iterable[dict[str, Any]], fallback_category_id: int | None = None) -> int | None:
    """Apply the relevant category rule or return the fallback category."""
    match = match_rule(description, rules)
    if match is None:
        return fallback_category_id
    if match.action == "ignore":
        return None
    return match.category_id if match.category_id is not None else fallback_category_id
