from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database
from database import Base
from resume_mcp.persistence import McpWorkflowStore


def workflow_store(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'mcp.db'}", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", session_local)
    Base.metadata.create_all(bind=engine)
    return McpWorkflowStore()


def test_workflow_is_scoped_to_poke_user(tmp_path, monkeypatch):
    store = workflow_store(tmp_path, monkeypatch)
    workflow = store.create(
        poke_user_id="poke-a",
        job_description="Build reliable software and integrations. " * 5,
    )

    assert store.get_for_user(workflow["id"], "poke-a")["id"] == workflow["id"]
    assert store.get_for_user(workflow["id"], "poke-b") is None


def test_pending_action_id_is_stable_until_action_type_changes(tmp_path, monkeypatch):
    store = workflow_store(tmp_path, monkeypatch)
    workflow = store.create(
        poke_user_id="poke-a",
        job_description="Build reliable software and integrations. " * 5,
    )
    first = store.set_action(
        workflow["id"], "poke-a",
        action_type="select_contact_identity",
        question="Choose an identity.",
    )
    repeated = store.set_action(
        workflow["id"], "poke-a",
        action_type="select_contact_identity",
        question="Choose an identity again.",
    )
    changed = store.set_action(
        workflow["id"], "poke-a",
        action_type="retry_generation",
        question="Retry?",
    )

    assert first["pending_action"]["action_id"] == repeated["pending_action"]["action_id"]
    assert changed["pending_action"]["action_id"] != repeated["pending_action"]["action_id"]
