from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql

import database


MIGRATION_COLUMN_NAMES = {
    "resume_revision",
    "resume_versions",
    "active_resume_version",
    "pdf_revision",
    "pdf_generated_at",
    "audit_status",
    "audit_result",
    "audit_proposal",
    "audit_base_revision",
    "audit_base_hash",
    "audit_created_at",
    "audit_applied_at",
}


def test_sqlite_legacy_resume_drafts_migration_is_idempotent(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE resume_drafts ("
            "id VARCHAR(80) PRIMARY KEY, "
            "status VARCHAR(60), "
            "updated_at DATETIME, "
            "pdf_stale BOOLEAN NOT NULL DEFAULT false, "
            "pdf_path TEXT"
            ")"
        ))
        connection.execute(
            text(
                "INSERT INTO resume_drafts "
                "(id, status, updated_at, pdf_stale, pdf_path) "
                "VALUES (:id, :status, :updated_at, false, :pdf_path)"
            ),
            {
                "id": "legacy-draft",
                "status": "pdf_ready",
                "updated_at": "2026-07-20 12:34:56+00:00",
                "pdf_path": "/tmp/legacy.pdf",
            },
        )

    monkeypatch.setattr(database, "engine", engine)
    database.init_db()

    columns_after_first_run = {
        column["name"] for column in inspect(engine).get_columns("resume_drafts")
    }
    assert MIGRATION_COLUMN_NAMES <= columns_after_first_run
    with engine.connect() as connection:
        migrated_row = connection.execute(
            text(
                "SELECT id, resume_revision, pdf_revision, pdf_generated_at, "
                "resume_versions, active_resume_version, "
                "audit_status, audit_result, audit_proposal, audit_base_revision, "
                "audit_base_hash, audit_created_at, audit_applied_at "
                "FROM resume_drafts WHERE id = :id"
            ),
            {"id": "legacy-draft"},
        ).mappings().one()

    assert migrated_row["id"] == "legacy-draft"
    assert migrated_row["resume_revision"] == 1
    assert migrated_row["resume_versions"] is None
    assert migrated_row["active_resume_version"] is None
    assert migrated_row["pdf_revision"] == 1
    assert migrated_row["pdf_generated_at"] == "2026-07-20 12:34:56+00:00"
    assert migrated_row["audit_status"] == "not_started"
    assert all(
        migrated_row[name] is None
        for name in (
            "audit_result",
            "audit_proposal",
            "audit_base_revision",
            "audit_base_hash",
            "audit_created_at",
            "audit_applied_at",
        )
    )

    database.init_db()

    columns_after_second_run = {
        column["name"] for column in inspect(engine).get_columns("resume_drafts")
    }
    with engine.connect() as connection:
        row_count = connection.execute(
            text("SELECT count(*) FROM resume_drafts WHERE id = :id"),
            {"id": "legacy-draft"},
        ).scalar_one()
    assert columns_after_second_run == columns_after_first_run
    assert row_count == 1


def test_postgresql_addition_definitions_use_dialect_types():
    statements = database._resume_draft_addition_statements(
        postgresql.dialect(),
        set(),
    )
    compiled = "\n".join(statements)

    assert "DATETIME" not in compiled.upper()
    assert '"resume_revision" INTEGER DEFAULT 1 NOT NULL' in compiled
    assert '"resume_versions" JSON' in compiled
    assert '"active_resume_version" VARCHAR(40)' in compiled
    assert '"pdf_revision" INTEGER' in compiled
    assert compiled.count("TIMESTAMP WITH TIME ZONE") == 3
    assert '"audit_status" VARCHAR(40) DEFAULT \'not_started\' NOT NULL' in compiled
    assert '"audit_result" JSON' in compiled
    assert '"audit_proposal" JSON' in compiled
    assert '"audit_base_revision" INTEGER' in compiled
    assert '"audit_base_hash" VARCHAR(80)' in compiled
    assert all(statement.startswith('ALTER TABLE "resume_drafts"') for statement in statements)


def test_postgresql_pdf_backfill_uses_boolean_expression():
    compiled = str(
        database._resume_draft_pdf_backfill_statement().compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert '"pdf_stale" IS false' in compiled
    assert '"pdf_stale" = 0' not in compiled
    assert '"pdf_stale" IS 0' not in compiled


def test_postgresql_migration_emits_alters_only_for_missing_columns():
    class CaptureConnection:
        dialect = postgresql.dialect()

        def __init__(self):
            self.statements = []

        def execute(self, statement):
            self.statements.append(str(statement.compile(
                dialect=self.dialect,
                compile_kwargs={"literal_binds": True},
            )))

    existing_columns = MIGRATION_COLUMN_NAMES - {
        "pdf_generated_at",
        "audit_result",
    }
    connection = CaptureConnection()

    database._apply_resume_draft_migration(connection, existing_columns)

    alter_statements = [
        statement
        for statement in connection.statements
        if statement.startswith("ALTER TABLE")
    ]
    assert len(alter_statements) == 2
    assert any('"pdf_generated_at" TIMESTAMP WITH TIME ZONE' in statement for statement in alter_statements)
    assert any('"audit_result" JSON' in statement for statement in alter_statements)
    assert all('"resume_revision"' not in statement for statement in alter_statements)
    assert connection.statements[-1].startswith('UPDATE "resume_drafts"')
