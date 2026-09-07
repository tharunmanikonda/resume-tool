from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app as resume_app
import database
import job_discovery
from database import Base, JobLead, JobSource, session_scope


def setup_discovery_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'job-discovery.db'}", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    monkeypatch.setattr(database, "SessionLocal", session_local)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(job_discovery, "check_cpt_company", lambda _company: {"status": "green"})
    return engine


def candidate(job_id="job-1", title="Backend Software Engineer", description="Build Python services."):
    return job_discovery.JobCandidate(
        source="greenhouse",
        source_company_key="acme",
        external_job_id=job_id,
        company_name="Acme",
        role_title=title,
        location="Remote US",
        job_url=f"https://boards.greenhouse.io/acme/jobs/{job_id}",
        apply_url=f"https://boards.greenhouse.io/acme/jobs/{job_id}",
        posted_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
        description=description,
        raw_snapshot={"id": job_id, "title": title},
    )


def create_source_row():
    with session_scope() as db:
        row = JobSource(
            id="source-1",
            source_type="greenhouse",
            name="Acme",
            company_name="Acme",
            source_key="acme",
            enabled=True,
            scan_frequency="daily",
        )
        db.add(row)


def test_identity_hash_uses_ats_id_not_recency():
    first = candidate(job_id="123", title="Backend Software Engineer")
    second = candidate(job_id="123", title="Frontend Software Engineer")

    assert job_discovery.identity_hash_for(first) == job_discovery.identity_hash_for(second)
    assert job_discovery.content_hash_for(first) != job_discovery.content_hash_for(second)


def test_scan_repeated_job_does_not_duplicate_and_changed_content_updates(tmp_path, monkeypatch):
    setup_discovery_db(tmp_path, monkeypatch)
    create_source_row()
    calls = [
        [candidate(description="Build Python services.")],
        [candidate(description="Build Python services and React tools.")],
    ]
    monkeypatch.setitem(job_discovery.FETCHERS, "greenhouse", lambda _source: calls.pop(0))

    first = job_discovery.scan_source("source-1")
    second = job_discovery.scan_source("source-1")

    with session_scope() as db:
        rows = db.query(JobLead).all()
        assert len(rows) == 1
        assert rows[0].job_description == "Build Python services and React tools."
    assert first["new"] == 1
    assert second["updated"] == 1


def test_hidden_reappearing_job_stays_hidden(tmp_path, monkeypatch):
    setup_discovery_db(tmp_path, monkeypatch)
    create_source_row()
    monkeypatch.setitem(job_discovery.FETCHERS, "greenhouse", lambda _source: [candidate()])

    job_discovery.scan_source("source-1")
    lead = job_discovery.list_leads({"fresh": "true"})["leads"][0]
    job_discovery.update_lead(lead["id"], {"status": "hidden"})
    job_discovery.scan_source("source-1")

    with session_scope() as db:
        row = db.query(JobLead).one()
        assert row.status == "hidden"
        assert row.missing_seen_count == 0


def test_missing_jobs_become_stale_then_closed(tmp_path, monkeypatch):
    setup_discovery_db(tmp_path, monkeypatch)
    create_source_row()
    monkeypatch.setitem(job_discovery.FETCHERS, "greenhouse", lambda _source: [candidate()])
    job_discovery.scan_source("source-1")
    monkeypatch.setitem(job_discovery.FETCHERS, "greenhouse", lambda _source: [])

    for _ in range(3):
        job_discovery.scan_source("source-1")
    with session_scope() as db:
        assert db.query(JobLead).one().status == "stale"

    for _ in range(7):
        job_discovery.scan_source("source-1")
    with session_scope() as db:
        assert db.query(JobLead).one().status == "closed"


def test_job_source_and_lead_apis_scan_and_promote(tmp_path, monkeypatch):
    setup_discovery_db(tmp_path, monkeypatch)
    monkeypatch.setitem(job_discovery.FETCHERS, "greenhouse", lambda _source: [
        candidate(description="Build reliable backend services with Python and PostgreSQL. " * 4)
    ])
    monkeypatch.setattr(resume_app, "has_permanent_profile_doc", lambda: True)
    monkeypatch.setattr(resume_app, "extension_profile_snapshot", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(resume_app, "tracker_company_history", lambda _company: {"count": 0, "applications": []})
    monkeypatch.setattr(resume_app.extension_worker_event, "set", lambda: None)

    client = resume_app.app.test_client()
    source_response = client.post("/api/job-sources", json={
        "source_type": "greenhouse",
        "name": "Acme",
        "company_name": "Acme",
        "source_key": "acme",
    })
    assert source_response.status_code == 200
    source_id = source_response.get_json()["source"]["id"]

    scan_response = client.post(f"/api/job-sources/{source_id}/scan")
    assert scan_response.status_code == 200
    assert scan_response.get_json()["result"]["new"] == 1

    leads_response = client.get("/api/job-leads?fresh=true")
    lead_id = leads_response.get_json()["leads"][0]["id"]
    promote_response = client.post(f"/api/job-leads/{lead_id}/promote-to-draft")

    assert promote_response.status_code == 200
    assert promote_response.get_json()["draft"]["job_lead_id"] == lead_id
    assert job_discovery.get_lead(lead_id)["status"] == "draft_created"
