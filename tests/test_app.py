from sqlalchemy import create_engine, inspect

from intelligent_chat.storage.models import Base


def test_schema_creates_all_tables():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    tables = set(inspect(engine).get_table_names())
    expected = {
        "users", "workspaces", "workspace_members", "projects", "project_members",
        "sessions", "messages", "concepts", "concept_tags", "relationships",
        "evidence", "governance_issues", "okf_export_log", "audit_log",
    }
    assert expected == tables


def test_insert_and_query_concept():
    from sqlalchemy.orm import Session

    from intelligent_chat.storage.models import Concept, User, Workspace

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        user = User(email="test@example.com", name="Test User")
        session.add(user)
        session.flush()

        workspace = Workspace(name="test-workspace", owner_id=user.id)
        session.add(workspace)
        session.flush()

        concept = Concept(
            workspace_id=workspace.id,
            title="SQLAlchemy Setup",
            type="decision",
            description="Use SQLAlchemy 2.0 with mapped_column style.",
            confidence="extracted",
        )
        session.add(concept)
        session.commit()

        result = session.get(Concept, concept.id)
        assert result is not None
        assert result.title == "SQLAlchemy Setup"
        assert result.type == "decision"
