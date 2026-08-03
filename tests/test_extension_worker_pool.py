import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app as resume_app
import database
from database import Base, ResumeDraftTask, session_scope
from extension_drafts import ExtensionDraftStore


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (None, 2),
        ("", 2),
        ("invalid", 2),
        ("0", 1),
        ("1", 1),
        ("3", 3),
        ("9", 4),
    ],
)
def test_extension_generation_worker_count_uses_default_and_bounds(monkeypatch, configured, expected):
    if configured is None:
        monkeypatch.delenv("EXTENSION_GENERATION_WORKERS", raising=False)
    else:
        monkeypatch.setenv("EXTENSION_GENERATION_WORKERS", configured)

    assert resume_app.extension_generation_worker_count() == expected


def test_extension_worker_pool_recovers_once_and_starts_configured_workers_once(monkeypatch):
    recovered = []
    created = []

    class FakeStore:
        def recover_interrupted(self):
            recovered.append("recovered")

    class FakeThread:
        def __init__(self, *, target, name, daemon):
            self.target = target
            self.name = name
            self.daemon = daemon
            self.start_count = 0
            created.append(self)

        def start(self):
            self.start_count += 1

    monkeypatch.setenv("EXTENSION_GENERATION_WORKERS", "3")
    monkeypatch.setattr(resume_app, "extension_drafts", FakeStore())
    monkeypatch.setattr(resume_app.threading, "Thread", FakeThread)
    monkeypatch.setattr(resume_app, "extension_worker_started", False)
    monkeypatch.setattr(resume_app, "extension_worker_threads", [])

    resume_app.ensure_extension_worker_started()
    resume_app.ensure_extension_worker_started()

    assert recovered == ["recovered"]
    assert [thread.name for thread in created] == [
        "resume-draft-worker-1",
        "resume-draft-worker-2",
        "resume-draft-worker-3",
    ]
    assert all(thread.daemon for thread in created)
    assert [thread.start_count for thread in created] == [1, 1, 1]
    assert resume_app.extension_worker_threads == created


def test_two_workers_execute_distinct_tasks_concurrently():
    stop_event = threading.Event()
    wake_event = threading.Event()
    release = threading.Event()
    both_started = threading.Event()
    state_lock = threading.Lock()
    started = []
    completed = []

    class QueueStore:
        def __init__(self):
            self._lock = threading.Lock()
            self._tasks = [
                {"task_id": "task-1", "draft": {"id": "draft-1"}},
                {"task_id": "task-2", "draft": {"id": "draft-2"}},
            ]

        def has_duplicate_review(self):
            return False

        def next_task(self):
            with self._lock:
                return self._tasks.pop(0) if self._tasks else None

    def run_task(task):
        with state_lock:
            started.append(task["draft"]["id"])
            if len(started) == 2:
                both_started.set()
        assert release.wait(timeout=2)
        with state_lock:
            completed.append(task["draft"]["id"])
            if len(completed) == 2:
                stop_event.set()
                wake_event.set()

    store = QueueStore()
    workers = [
        threading.Thread(
            target=resume_app.extension_worker_loop,
            args=(stop_event, store, run_task, wake_event),
            name=f"test-resume-worker-{index + 1}",
        )
        for index in range(2)
    ]
    for worker in workers:
        worker.start()

    assert both_started.wait(timeout=2)
    assert set(started) == {"draft-1", "draft-2"}
    assert completed == []
    release.set()
    for worker in workers:
        worker.join(timeout=2)

    assert all(not worker.is_alive() for worker in workers)
    assert set(completed) == {"draft-1", "draft-2"}


def test_store_never_claims_two_tasks_for_the_same_draft(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'worker-pool.db'}", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", session_local)
    Base.metadata.create_all(bind=engine)
    store = ExtensionDraftStore()
    draft = store.create(
        {
            "source": "linkedin",
            "external_job_id": "single-draft",
            "company_name": "Acme",
            "role_title": "Software Engineer",
            "job_description": "Build reliable software systems. " * 8,
        },
        {
            "identity_id": "outlook",
            "enabled_experience_keys": [],
            "profile_snapshot": {},
            "contact_snapshot": {},
            "experience_history_snapshot": [],
        },
        0,
    )
    with session_scope() as db:
        db.add(ResumeDraftTask(id="task-duplicate", draft_id=draft["id"], status="queued", stage="waiting"))

    start = threading.Barrier(3)
    claims = []
    claims_lock = threading.Lock()

    def claim_task():
        start.wait(timeout=2)
        claimed = store.next_task()
        with claims_lock:
            claims.append(claimed)

    claimers = [threading.Thread(target=claim_task) for _ in range(2)]
    for claimer in claimers:
        claimer.start()
    start.wait(timeout=2)
    for claimer in claimers:
        claimer.join(timeout=2)

    assert all(not claimer.is_alive() for claimer in claimers)
    claimed_tasks = [claim for claim in claims if claim is not None]
    assert len(claimed_tasks) == 1
    assert claimed_tasks[0]["draft"]["id"] == draft["id"]

