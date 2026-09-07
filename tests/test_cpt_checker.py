from __future__ import annotations

from datetime import timedelta

import pytest

from cpt_checker import (
    CptEmployerRow,
    check_cpt_company,
    classify_cpt_row,
    find_cpt_employer,
    normalize_company_name,
)
from database import Base, CptCompanyCheck, engine, session_scope, utcnow


@pytest.fixture(autouse=True)
def ensure_cpt_table():
    Base.metadata.create_all(bind=engine)


def test_normalizes_company_suffixes_and_punctuation():
    assert normalize_company_name("Meta Platforms, Inc.") == "meta"
    assert normalize_company_name("Acme LLC") == "acme"
    assert normalize_company_name("JPMorgan Chase") == "jpmorganchase"


def test_conservative_match_allows_generic_suffix_alias():
    rows = [
        CptEmployerRow("Meta Platforms", "Technology", False, False, "Supporting"),
        CptEmployerRow("Metabase", "Technology", True, True, "Supporting"),
    ]

    assert find_cpt_employer("Meta", rows).company == "Meta Platforms"


def test_conservative_match_avoids_unrelated_prefixes():
    rows = [
        CptEmployerRow("Apple", "Technology", False, False, "Not Supporting"),
        CptEmployerRow("Applied Materials", "Hardware", False, False, "Not Supporting"),
    ]

    assert find_cpt_employer("App", rows) is None


@pytest.mark.parametrize(
    ("row", "status"),
    [
        (CptEmployerRow("Block", "Technology", True, False, "Supporting"), "green"),
        (CptEmployerRow("Cisco", "Technology", False, True, "Unknown"), "green"),
        (CptEmployerRow("Apple", "Technology", False, False, "Not Supporting"), "red"),
        (CptEmployerRow("Citi", "Finance", True, False, "Depends"), "review"),
        (CptEmployerRow("Adobe", "Technology", True, False, "Unknown"), "review"),
        (None, "not_found"),
    ],
)
def test_cpt_classification_is_advisory(row, status):
    result = classify_cpt_row("Example", row)

    assert result["blocked"] is False
    assert result["status"] == status


def test_fresh_cached_result_avoids_refetch():
    first = check_cpt_company(
        "Block",
        force_refresh=True,
        fetcher=lambda: """
        <table><tr><th>Company</th><th>Industry</th><th>CPT Friendly</th><th>CPT Onboard</th><th>CPT Agreement</th></tr>
        <tr><td>Block</td><td>Technology</td><td>✓</td><td>✓</td><td>Supporting</td></tr></table>
        """,
    )

    def fail_fetcher():
        raise AssertionError("fresh cache should not fetch")

    second = check_cpt_company("Block", fetcher=fail_fetcher)

    assert first["blocked"] is False
    assert second["blocked"] is False
    assert second["matched_company_name"] == "Block"


def test_expired_cached_result_refreshes():
    now = utcnow()
    with session_scope() as db:
        row = db.query(CptCompanyCheck).filter(CptCompanyCheck.normalized_company_name == "expiredco").first()
        if row:
            db.delete(row)
        db.add(CptCompanyCheck(
            id="cpt-expired-test",
            company_name="Expired Co",
            normalized_company_name="expiredco",
            matched_company_name="Expired Co",
            status="red",
            blocked=True,
            cpt_friendly=False,
            cpt_onboard=False,
            cpt_agreement="Not Supporting",
            message="old",
            source_url="https://day1cpt.org/day-1-cpt/employers",
            source_snapshot={},
            checked_at=now - timedelta(days=10),
            expires_at=now - timedelta(days=1),
        ))

    refreshed = check_cpt_company(
        "Expired Co",
        fetcher=lambda: """
        <table><tr><th>Company</th><th>Industry</th><th>CPT Friendly</th><th>CPT Onboard</th><th>CPT Agreement</th></tr>
        <tr><td>Expired Co</td><td>Technology</td><td>✓</td><td>✓</td><td>Supporting</td></tr></table>
        """,
    )

    assert refreshed["blocked"] is False
    assert refreshed["cpt_onboard"] is True


def test_fetch_failure_without_cache_blocks():
    result = check_cpt_company(
        "No Cache Co",
        force_refresh=True,
        fetcher=lambda: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    assert result["blocked"] is False
    assert "unavailable" in result["message"].lower()
