"""Day1CPT company eligibility checks with a short-lived local cache."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Callable
import urllib.request

from sqlalchemy import select

from database import CptCompanyCheck, session_scope, utcnow


DAY1CPT_EMPLOYERS_URL = "https://day1cpt.org/day-1-cpt/employers"
CPT_CACHE_TTL = timedelta(days=7)
COMPANY_SUFFIXES = {
    "co", "company", "corp", "corporation", "inc", "incorporated", "llc", "ltd",
    "limited", "plc", "group", "holdings", "holding", "technologies", "technology",
    "systems", "solutions", "labs", "platforms", "usa", "us",
}


@dataclass(frozen=True)
class CptEmployerRow:
    company: str
    industry: str
    cpt_friendly: bool
    cpt_onboard: bool
    cpt_agreement: str


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None
        self._cell_tag = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "table":
            self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []
            self._cell_tag = tag

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            value = re.sub(r"\s+", " ", data).strip()
            if value:
                self._current_cell.append(value)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            self._current_row.append(" ".join(self._current_cell).strip())
            self._current_cell = None
            self._cell_tag = ""
        elif tag == "tr" and self._current_row is not None and self._current_table is not None:
            if any(cell.strip() for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._current_table is not None:
            self.tables.append(self._current_table)
            self._current_table = None


def normalize_company_name(value: str) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split()
    while len(words) > 1 and words[-1] in COMPANY_SUFFIXES:
        words.pop()
    return "".join(words)


def _company_words(value: str) -> list[str]:
    words = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split()
    while len(words) > 1 and words[-1] in COMPANY_SUFFIXES:
        words.pop()
    return words


def _truthy(value: str) -> bool:
    compact = str(value or "").strip().lower()
    return compact in {"true", "yes", "y", "1", "✓", "✔", "check", "checked"}


def fetch_day1cpt_html(timeout: int = 15) -> str:
    request = urllib.request.Request(
        DAY1CPT_EMPLOYERS_URL,
        headers={"User-Agent": "resume-tool-cpt-checker/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_day1cpt_employers(html: str) -> list[CptEmployerRow]:
    parser = _TableParser()
    parser.feed(html or "")
    for table in parser.tables:
        if not table:
            continue
        header_index = next(
            (
                index for index, row in enumerate(table)
                if len(row) >= 5
                and normalize_company_name(row[0]) == "company"
                and normalize_company_name(row[1]) == "industry"
                and "cpt" in row[2].lower()
                and "friendly" in row[2].lower()
            ),
            None,
        )
        if header_index is None:
            continue
        rows: list[CptEmployerRow] = []
        for row in table[header_index + 1:]:
            if len(row) < 5:
                continue
            company = row[0].strip()
            if not company or company.lower() in {"company", "date"}:
                continue
            rows.append(CptEmployerRow(
                company=company,
                industry=row[1].strip(),
                cpt_friendly=_truthy(row[2]),
                cpt_onboard=_truthy(row[3]),
                cpt_agreement=row[4].strip() or "Unknown",
            ))
        if rows:
            return rows
    return []


def _matches_company(query: str, candidate: str) -> bool:
    query_normalized = normalize_company_name(query)
    candidate_normalized = normalize_company_name(candidate)
    if not query_normalized or not candidate_normalized:
        return False
    if query_normalized == candidate_normalized:
        return True
    query_words = _company_words(query)
    candidate_words = _company_words(candidate)
    if len(query_words) == 1 and query_words[0] == candidate_words[0] and len(query_words[0]) >= 4:
        return all(word in COMPANY_SUFFIXES for word in candidate_words[1:])
    if len(candidate_words) == 1 and candidate_words[0] == query_words[0] and len(candidate_words[0]) >= 4:
        return all(word in COMPANY_SUFFIXES for word in query_words[1:])
    return False


def find_cpt_employer(company_name: str, rows: list[CptEmployerRow]) -> CptEmployerRow | None:
    exact = [
        row for row in rows
        if normalize_company_name(company_name) == normalize_company_name(row.company)
    ]
    if exact:
        return exact[0]
    conservative = [row for row in rows if _matches_company(company_name, row.company)]
    return conservative[0] if len(conservative) == 1 else None


def classify_cpt_row(company_name: str, row: CptEmployerRow | None, *, now: datetime | None = None) -> dict:
    current_time = now or utcnow()
    expires_at = current_time + CPT_CACHE_TTL
    base = {
        "company_name": company_name,
        "source_url": DAY1CPT_EMPLOYERS_URL,
        "checked_at": current_time.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    if row is None:
        return {
            **base,
            "status": "not_found",
            "blocked": False,
            "matched_company_name": "",
            "cpt_friendly": False,
            "cpt_onboard": False,
            "cpt_agreement": "Not Found",
            "message": "Company was not found in the Day1CPT employer list. This does not prove the company rejects CPT; review before applying.",
            "source_snapshot": {"found": False},
        }

    agreement = row.cpt_agreement or "Unknown"
    agreement_key = agreement.strip().lower()
    green = bool(row.cpt_onboard or agreement_key == "supporting")
    red = agreement_key in {"not supporting", "not supported", "no", "false"}
    status = "green" if green else "red" if red else "review"
    return {
        **base,
        "status": status,
        "blocked": False,
        "matched_company_name": row.company,
        "cpt_friendly": bool(row.cpt_friendly),
        "cpt_onboard": bool(row.cpt_onboard),
        "cpt_agreement": agreement,
        "message": (
            "Company appears CPT onboarding friendly according to Day1CPT."
            if green else
            f"Company is listed on Day1CPT as {agreement or 'Unknown'}. Resume generation can continue, but review before applying."
        ),
        "source_snapshot": {
            "found": True,
            "company": row.company,
            "industry": row.industry,
            "cpt_friendly": bool(row.cpt_friendly),
            "cpt_onboard": bool(row.cpt_onboard),
            "cpt_agreement": agreement,
        },
    }


def _serialize_check(row: CptCompanyCheck, *, warning: str = "") -> dict:
    checked_at = row.checked_at.replace(tzinfo=timezone.utc) if row.checked_at and row.checked_at.tzinfo is None else row.checked_at
    expires_at = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at and row.expires_at.tzinfo is None else row.expires_at
    return {
        "status": row.status,
        "blocked": bool(row.blocked),
        "company_name": row.company_name,
        "matched_company_name": row.matched_company_name or "",
        "cpt_friendly": bool(row.cpt_friendly),
        "cpt_onboard": bool(row.cpt_onboard),
        "cpt_agreement": row.cpt_agreement or "",
        "source_url": row.source_url,
        "checked_at": checked_at.isoformat() if checked_at else "",
        "expires_at": expires_at.isoformat() if expires_at else "",
        "message": row.message,
        "source_snapshot": row.source_snapshot or {},
        "warning": warning,
    }


def _upsert_check(result: dict) -> dict:
    normalized = normalize_company_name(result["company_name"])
    with session_scope() as db:
        row = db.scalars(
            select(CptCompanyCheck)
            .where(CptCompanyCheck.normalized_company_name == normalized)
            .order_by(CptCompanyCheck.checked_at.desc())
        ).first()
        checked_at = datetime.fromisoformat(result["checked_at"])
        expires_at = datetime.fromisoformat(result["expires_at"])
        values = {
            "company_name": result["company_name"],
            "normalized_company_name": normalized,
            "matched_company_name": result.get("matched_company_name") or None,
            "status": result["status"],
            "blocked": bool(result["blocked"]),
            "cpt_friendly": bool(result["cpt_friendly"]),
            "cpt_onboard": bool(result["cpt_onboard"]),
            "cpt_agreement": result.get("cpt_agreement") or "",
            "message": result["message"],
            "source_url": result["source_url"],
            "source_snapshot": result.get("source_snapshot") or {},
            "checked_at": checked_at,
            "expires_at": expires_at,
        }
        if row is None:
            row = CptCompanyCheck(id=f"cpt-{uuid.uuid4().hex}", **values)
            db.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        db.flush()
        return _serialize_check(row)


def check_cpt_company(
    company_name: str,
    *,
    force_refresh: bool = False,
    now: datetime | None = None,
    fetcher: Callable[[], str] | None = None,
) -> dict:
    current_time = now or utcnow()
    clean_company = str(company_name or "").strip()
    if not clean_company:
        return {
            "status": "red",
            "blocked": False,
            "company_name": "",
            "matched_company_name": "",
            "cpt_friendly": False,
            "cpt_onboard": False,
            "cpt_agreement": "Missing Company",
            "source_url": DAY1CPT_EMPLOYERS_URL,
            "checked_at": current_time.isoformat(),
            "expires_at": current_time.isoformat(),
            "message": "Company name is required before checking CPT onboarding status. Resume generation can continue.",
            "source_snapshot": {"found": False},
        }

    normalized = normalize_company_name(clean_company)
    cached: CptCompanyCheck | None = None
    with session_scope() as db:
        cached = db.scalars(
            select(CptCompanyCheck)
            .where(CptCompanyCheck.normalized_company_name == normalized)
            .order_by(CptCompanyCheck.checked_at.desc())
        ).first()
        cached_expires_at = (
            cached.expires_at.replace(tzinfo=timezone.utc)
            if cached and cached.expires_at and cached.expires_at.tzinfo is None
            else cached.expires_at if cached else None
        )
        if cached and not force_refresh and cached_expires_at and cached_expires_at > current_time:
            return _serialize_check(cached)
        cached_payload = _serialize_check(cached) if cached else None

    try:
        html = (fetcher or fetch_day1cpt_html)()
        rows = parse_day1cpt_employers(html)
        if not rows:
            raise RuntimeError("Could not read the Day1CPT employers table.")
        result = classify_cpt_row(clean_company, find_cpt_employer(clean_company, rows), now=current_time)
        return _upsert_check(result)
    except Exception as exc:
        if cached_payload:
            cached_payload["warning"] = f"Could not refresh Day1CPT; using the last saved CPT result. {exc}"
            return cached_payload
        return {
            "status": "red",
            "blocked": False,
            "company_name": clean_company,
            "matched_company_name": "",
            "cpt_friendly": False,
            "cpt_onboard": False,
            "cpt_agreement": "Unavailable",
            "source_url": DAY1CPT_EMPLOYERS_URL,
            "checked_at": current_time.isoformat(),
            "expires_at": current_time.isoformat(),
            "message": "CPT status is unavailable because Day1CPT could not be checked. Resume generation can continue.",
            "source_snapshot": {"found": False, "error": str(exc)},
            "warning": str(exc),
        }
