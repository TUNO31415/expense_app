from __future__ import annotations

import csv
from difflib import SequenceMatcher
import hashlib
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable

from services.categorizer import match_rule

_CATEGORY_NUMBER_PREFIX = re.compile(r"^\s*\d+\s*[.)-]\s*")


def _normalize_category_name(value: str) -> str:
    text = _CATEGORY_NUMBER_PREFIX.sub("", str(value or "").strip()).casefold()
    tokens = re.findall(r"\w+", text)
    normalized_tokens = [
        token[:-3] + "y"
        if token.endswith("ies") and len(token) > 4
        else token[:-1]
        if token.endswith("s") and not token.endswith("ss") and len(token) > 3
        else token
        for token in tokens
    ]
    return " ".join(normalized_tokens)


def _category_similarity(query: str, candidate: str) -> float:
    query_tokens = set(query.split())
    candidate_tokens = set(candidate.split())
    token_overlap = (
        len(query_tokens & candidate_tokens) / min(len(query_tokens), len(candidate_tokens))
        if query_tokens and candidate_tokens
        else 0.0
    )
    return max(SequenceMatcher(None, query, candidate).ratio(), token_overlap)

def resolve_category(
    category_name: str,
    type_name: str,
    categories: Iterable[dict[str, Any]],
    *,
    similarity_threshold: float = 0.80,
    minimum_margin: float = 0.08,
) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve a CSV category within its type, returning a suggestion if uncertain."""
    query = _normalize_category_name(category_name)
    normalized_type = str(type_name or "").strip().casefold()
    if not query or not normalized_type:
        return None, None

    candidates = [
        category
        for category in categories
        if str(category.get("type_name") or "").strip().casefold() == normalized_type
    ]
    exact_matches = [
        category for category in candidates if _normalize_category_name(category.get("name", "")) == query
    ]
    if len(exact_matches) == 1:
        return exact_matches[0], exact_matches[0]["name"]

    scored = sorted(
        (
            (_category_similarity(query, _normalize_category_name(category.get("name", ""))), category)
            for category in candidates
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored:
        return None, None

    best_score, best_category = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    suggestion = best_category["name"]
    if best_score >= similarity_threshold and best_score - second_score >= minimum_margin:
        return best_category, suggestion
    return None, suggestion


def suggest_column_mapping(
    columns: Iterable[str], aliases: dict[str, Iterable[str]]
) -> dict[str, str | None]:
    """Suggest CSV columns by case-insensitive header name without guessing."""
    available = {str(column).strip().casefold(): column for column in columns}
    return {
        field: next(
            (available[alias.strip().casefold()] for alias in names if alias.strip().casefold() in available),
            None,
        )
        for field, names in aliases.items()
    }


def detect_encoding(data: bytes) -> str:
    """Pick UTF-8 when possible, otherwise fall back to Latin-1."""
    for candidate in ("utf-8-sig", "utf-8"):
        try:
            data.decode(candidate)
            return "utf-8"
        except UnicodeDecodeError:
            continue
    return "latin-1"


def detect_delimiter(csv_text: str) -> str:
    """Choose the most likely CSV delimiter from the first data rows."""
    lines = [line for line in csv_text.splitlines() if line.strip() and not line.lstrip().startswith("#")][:10]
    if not lines:
        return ","

    scores = {";": 0, ",": 0}
    for line in lines:
        for delimiter in (";", ","):
            scores[delimiter] += line.count(delimiter)

    return ";" if scores[";"] >= scores[","] else ","


def detect_decimal_separator(value: str) -> str:
    """Find whether the decimal separator is a comma or a dot in a numeric string."""
    text = str(value or "").strip()
    if not text:
        return "."

    if "," in text and "." in text:
        return "," if text.rfind(",") > text.rfind(".") else "."
    if "," in text:
        return ","
    if "." in text:
        return "."
    return "."


def parse_amount(value: Any, decimal_sep: str | None = None) -> float:
    """Normalize a bank or CSV value into a float in base units."""
    if value is None or value == "":
        raise ValueError("Amount is empty")
    text = str(value).strip().replace("€", "").replace(" ", "")
    if text in {"-", "+"}:
        raise ValueError("Amount is not numeric")

    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]

    if decimal_sep is None:
        decimal_sep = detect_decimal_separator(text)

    if decimal_sep == ",":
        if "." in text and "," in text:
            # European format: keep only last punctuation as decimal separator
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")

    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]

    try:
        return float(Decimal(text))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid amount: {value!r}") from exc


def parse_date(value: Any, fmt: str | None = None) -> str:
    """Parse a date-like field and return ISO YYYY-MM-DD."""
    if value is None or value == "":
        raise ValueError("Date is empty")

    if hasattr(value, "isoformat"):
        return str(value.date().isoformat())

    text = str(value).strip()
    if not text:
        raise ValueError("Date is empty")

    formats = [fmt] if fmt else [
        "%Y-%m-%d",
        "%Y%m%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%Y.%m.%d",
    ]

    for candidate in formats:
        if candidate is None:
            continue
        try:
            return datetime.strptime(text, candidate).date().isoformat()
        except ValueError:
            continue

    raise ValueError(f"Unparseable date: {value!r}")


def compute_import_hash(date: str, amount_cents: int, description: str | None, reference: str | None = None) -> str:
    """Create a stable SHA-256 hash for duplicate detection."""
    payload = f"{date}|{amount_cents}|{(description or '').strip()}|{reference or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dedupe_rows(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Remove rows with the same import hash while preserving order."""
    unique_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    skipped = 0

    for row in rows:
        amount_cents = int(row.get("amount_cents"))
        import_hash = row.get("import_hash") or compute_import_hash(
            str(row.get("date")),
            amount_cents,
            row.get("description"),
            row.get("reference"),
        )
        if import_hash in seen:
            skipped += 1
            continue
        seen.add(import_hash)
        row["import_hash"] = import_hash
        unique_rows.append(row)

    return unique_rows, skipped


def filter_outgoing_transactions(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Keep only outgoing transactions and normalize them to positive cents for import."""
    outgoing: list[dict[str, Any]] = []
    ignored = 0

    for row in rows:
        amount_value = row.get("amount")
        if amount_value is None and row.get("amount_cents") is not None:
            amount_value = row["amount_cents"] / 100

        debit_credit = str(row.get("debit_credit") or row.get("credit_debit") or "").strip().lower()
        is_debit = debit_credit in {"debit", "d", "withdrawal", "outgoing"}
        is_dutch_direction = debit_credit in {"af", "bij"}

        amount_float = parse_amount(amount_value) if amount_value is not None else 0.0
        amount_negative = amount_float < 0
        is_outgoing = debit_credit == "af" if is_dutch_direction else amount_negative or is_debit

        if not is_outgoing:
            ignored += 1
            continue

        cents = int(abs(round(amount_float * 100)))
        normalized = dict(row)
        normalized["amount_cents"] = cents
        normalized["description"] = row.get("description") or row.get("counterparty") or row.get("description/counterparty")
        normalized["reference"] = row.get("reference")
        normalized["date"] = parse_date(row.get("date"))
        outgoing.append(normalized)

    return outgoing, ignored


def read_csv_rows(file_bytes: bytes, *, encoding: str | None = None, delimiter: str | None = None) -> tuple[list[dict[str, str]], str, str]:
    """Read CSV data from bytes into list-of-dicts rows with named columns."""
    enc = detect_encoding(file_bytes) if encoding is None else encoding
    text = file_bytes.decode(enc)
    sep = detect_delimiter(text) if delimiter is None else delimiter

    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=sep)
    rows = [{key: value for key, value in row.items()} for row in reader if row]
    return rows, enc, sep


def build_bank_review_rows(
    csv_rows: Iterable[dict[str, Any]],
    mapping: dict[str, str | None],
    date_format: str | None,
    rules: Iterable[dict[str, Any]],
    categories: Iterable[dict[str, Any]],
    existing_matches_fn: Callable[[list[dict[str, Any]]], dict[tuple[str, int], list[dict[str, Any]]]],
) -> dict[str, Any]:
    """Turn raw statement rows into review rows: parse, keep outgoing, apply rules, flag duplicates.

    `mapping` holds the CSV column names for date, amount, description and (optionally) direction.
    Returns the review rows plus counts of invalid, incoming and rule-ignored rows.
    """
    date_col = mapping["date"]
    amount_col = mapping["amount"]
    description_col = mapping["description"]
    direction_col = mapping.get("direction")
    rule_list = list(rules)
    category_by_id = {int(entry["id"]): entry for entry in categories}

    normalized_rows = []
    invalid = 0
    for row in csv_rows:
        try:
            normalized_date = parse_date(row.get(date_col), fmt=date_format)
            raw_amount = row.get(amount_col)
            amount_value = parse_amount(raw_amount, decimal_sep=detect_decimal_separator(str(raw_amount or "")))
        except ValueError:
            invalid += 1
            continue
        normalized_rows.append(
            {
                "date": normalized_date,
                "amount": amount_value,
                "description": row.get(description_col, "") or "",
                "debit_credit": row.get(direction_col) if direction_col else "",
            }
        )

    outgoing, ignored_incoming = filter_outgoing_transactions(normalized_rows)

    candidates = []
    excluded_by_rules = 0
    for item in outgoing:
        rule = match_rule(str(item["description"] or ""), rule_list)
        if rule is not None and rule.action == "ignore":
            excluded_by_rules += 1
            continue
        rule_category = category_by_id.get(rule.category_id) if rule is not None and rule.category_id is not None else None
        candidates.append(
            {
                "date": item["date"],
                "description": item["description"],
                "amount_cents": item["amount_cents"],
                "category_id": int(rule_category["id"]) if rule_category else None,
                "rule_keyword": rule.keyword if rule_category else None,
            }
        )

    existing_matches = existing_matches_fn(candidates) if candidates else {}
    seen: set[tuple[str, int]] = set()
    for item in candidates:
        key = (item["date"], item["amount_cents"])
        stored = existing_matches.get(key, [])
        repeated = key in seen
        seen.add(key)
        if stored:
            item["existing_record"] = "; ".join(
                f"#{match['id']} {match['date']} €{match['amount_cents'] / 100:.2f} "
                f"{match['type']} / {match['category']}: {match['description']}"
                for match in stored
            )
        elif repeated:
            item["existing_record"] = "Same transaction appears earlier in this file."
        else:
            item["existing_record"] = ""
        item["possible_duplicate"] = bool(stored) or repeated

    return {
        "rows": candidates,
        "invalid": invalid,
        "ignored_incoming": ignored_incoming,
        "excluded_by_rules": excluded_by_rules,
    }
