"""Phase 2 tests — search service and OKF/graph exporters."""

from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from intelligent_chat.storage.models import (
    Base,
    Concept,
    ConceptTag,
    IngestSession,
    Project,
    Relationship,
    User,
    Workspace,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_db() -> tuple:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = Session(engine)
    user = User(email="test@example.com", name="Test")
    db.add(user)
    db.flush()
    workspace = Workspace(name="test", owner_id=user.id)
    db.add(workspace)
    db.flush()
    project = Project(workspace_id=workspace.id, name="myproject", visibility="workspace")
    db.add(project)
    db.commit()
    return engine, db, workspace.id, project.id


def seed_concepts(db: Session, workspace_id: int, project_id: int) -> list[Concept]:
    concepts = [
        Concept(
            workspace_id=workspace_id,
            title="SQLAlchemy Setup",
            type="decision",
            description="Use SQLAlchemy 2.0 with mapped_column.",
            body="Full body about SQLAlchemy async engine setup.",
            confidence="extracted",
            visibility="workspace",
        ),
        Concept(
            workspace_id=workspace_id,
            title="asyncpg Driver",
            type="tool",
            description="Fast async PostgreSQL driver.",
            body="asyncpg is the preferred driver for async SQLAlchemy.",
            confidence="extracted",
            visibility="workspace",
        ),
        Concept(
            workspace_id=workspace_id,
            project_id=project_id,
            title="Project DB Config",
            type="decision",
            description="This project uses synchronous SQLite for simplicity.",
            body="Sync SQLite engine chosen for CLI simplicity.",
            confidence="extracted",
            visibility="project",
        ),
    ]
    for c in concepts:
        db.add(c)
    db.flush()
    db.add(ConceptTag(concept_id=concepts[0].id, tag="python"))
    db.add(ConceptTag(concept_id=concepts[0].id, tag="database"))
    db.add(ConceptTag(concept_id=concepts[1].id, tag="database"))
    db.commit()
    return concepts


# ---------------------------------------------------------------------------
# Search service
# ---------------------------------------------------------------------------

class TestSearchConcepts:
    def test_text_search_finds_title_match(self):
        from intelligent_chat.search.service import search_concepts

        _, db, workspace_id, project_id = make_db()
        seed_concepts(db, workspace_id, project_id)

        results = search_concepts(db, workspace_id, "SQLAlchemy")
        assert len(results) >= 1
        titles = [r.title for r in results]
        assert "SQLAlchemy Setup" in titles

    def test_title_match_scores_higher_than_body_match(self):
        from intelligent_chat.search.service import search_concepts

        _, db, workspace_id, project_id = make_db()
        seed_concepts(db, workspace_id, project_id)

        results = search_concepts(db, workspace_id, "SQLAlchemy")
        # "SQLAlchemy Setup" has title match; "asyncpg Driver" has body match only
        assert results[0].title == "SQLAlchemy Setup"

    def test_filter_by_type(self):
        from intelligent_chat.search.service import search_concepts

        _, db, workspace_id, project_id = make_db()
        seed_concepts(db, workspace_id, project_id)

        results = search_concepts(db, workspace_id, "", concept_type="tool")
        assert all(r.type == "tool" for r in results)
        assert len(results) == 1

    def test_filter_by_tag(self):
        from intelligent_chat.search.service import search_concepts

        _, db, workspace_id, project_id = make_db()
        seed_concepts(db, workspace_id, project_id)

        results = search_concepts(db, workspace_id, "", tag="python")
        assert len(results) == 1
        assert results[0].title == "SQLAlchemy Setup"

    def test_visibility_filter_excludes_project_concepts(self):
        from intelligent_chat.search.service import search_concepts

        _, db, workspace_id, project_id = make_db()
        seed_concepts(db, workspace_id, project_id)

        # No project_ids provided → include_project_ids=[] → only workspace-visible
        results = search_concepts(db, workspace_id, "", include_project_ids=[])
        titles = [r.title for r in results]
        assert "Project DB Config" not in titles
        assert "SQLAlchemy Setup" in titles

    def test_visibility_filter_includes_project_concepts_when_member(self):
        from intelligent_chat.search.service import search_concepts

        _, db, workspace_id, project_id = make_db()
        seed_concepts(db, workspace_id, project_id)

        results = search_concepts(db, workspace_id, "", include_project_ids=[project_id])
        titles = [r.title for r in results]
        assert "Project DB Config" in titles

    def test_session_concepts_lookup(self):
        from intelligent_chat.search.service import get_session_concepts

        _, db, workspace_id, project_id = make_db()
        db.query(Project).filter_by(id=project_id).first()

        sess = IngestSession(
            id="test-session-001",
            workspace_id=workspace_id,
            project_id=project_id,
            source_type="claude_code",
            status="normalized",
        )
        db.add(sess)
        db.flush()

        concept = Concept(
            workspace_id=workspace_id,
            title="Session Concept",
            type="concept",
            description="From a test session.",
            confidence="extracted",
            visibility="workspace",
            resource="session:test-session-001",
        )
        db.add(concept)
        db.commit()

        results = get_session_concepts(db, workspace_id, "test-session-001")
        assert len(results) == 1
        assert results[0].title == "Session Concept"


# ---------------------------------------------------------------------------
# OKF exporter
# ---------------------------------------------------------------------------

class TestOKFExport:
    def test_export_creates_md_files(self, tmp_path):
        from intelligent_chat.export.okf import export_okf

        _, db, workspace_id, project_id = make_db()
        seed_concepts(db, workspace_id, project_id)

        result = export_okf(db, workspace_id=workspace_id, output_dir=tmp_path)

        assert result["exported"] == 3
        md_files = list(tmp_path.glob("*.md"))
        # 3 concepts + index.md = at least 4 files
        assert len(md_files) >= 4

    def test_export_has_valid_frontmatter(self, tmp_path):
        from intelligent_chat.export.okf import export_okf

        _, db, workspace_id, project_id = make_db()
        seed_concepts(db, workspace_id, project_id)
        export_okf(db, workspace_id=workspace_id, output_dir=tmp_path)

        content = (tmp_path / "sqlalchemy-setup.md").read_text()
        assert "type: decision" in content
        assert "title: SQLAlchemy Setup" in content
        assert "confidence: extracted" in content

    def test_index_md_lists_all_concepts(self, tmp_path):
        from intelligent_chat.export.okf import export_okf

        _, db, workspace_id, project_id = make_db()
        seed_concepts(db, workspace_id, project_id)
        export_okf(db, workspace_id=workspace_id, output_dir=tmp_path)

        index = (tmp_path / "index.md").read_text()
        assert "SQLAlchemy Setup" in index
        assert "asyncpg Driver" in index

    def test_log_md_is_appended(self, tmp_path):
        from intelligent_chat.export.okf import export_okf

        _, db, workspace_id, project_id = make_db()
        seed_concepts(db, workspace_id, project_id)
        export_okf(db, workspace_id=workspace_id, output_dir=tmp_path)
        export_okf(db, workspace_id=workspace_id, output_dir=tmp_path)

        log = (tmp_path / "log.md").read_text()
        assert log.count("export okf") == 2

    def test_visibility_filter_on_export(self, tmp_path):
        from intelligent_chat.export.okf import export_okf

        _, db, workspace_id, project_id = make_db()
        seed_concepts(db, workspace_id, project_id)

        # Export with no project access — project-scoped concept excluded
        result = export_okf(db, workspace_id=workspace_id, output_dir=tmp_path, project_ids=[])
        assert result["exported"] == 2


# ---------------------------------------------------------------------------
# Graph exporter
# ---------------------------------------------------------------------------

class TestGraphExport:
    def test_export_creates_graph_json(self, tmp_path):
        from intelligent_chat.export.graph import export_graph

        _, db, workspace_id, project_id = make_db()
        concepts = seed_concepts(db, workspace_id, project_id)

        # Add a relationship
        db.add(Relationship(
            workspace_id=workspace_id,
            source_concept_id=concepts[0].id,
            target_concept_id=concepts[1].id,
            relation_type="uses",
            confidence="extracted",
        ))
        db.commit()

        output = tmp_path / "graph.json"
        result = export_graph(db, workspace_id=workspace_id, output_path=output)

        assert output.exists()
        assert result["nodes"] > 0
        assert result["edges"] >= 1

    def test_graph_json_is_valid(self, tmp_path):
        from intelligent_chat.export.graph import export_graph

        _, db, workspace_id, project_id = make_db()
        seed_concepts(db, workspace_id, project_id)

        output = tmp_path / "graph.json"
        export_graph(db, workspace_id=workspace_id, output_path=output)

        data = json.loads(output.read_text())
        assert "nodes" in data
        assert "edges" in data
        assert "meta" in data
        assert data["meta"]["concept_count"] == 3

    def test_graph_nodes_have_required_fields(self, tmp_path):
        from intelligent_chat.export.graph import export_graph

        _, db, workspace_id, project_id = make_db()
        seed_concepts(db, workspace_id, project_id)

        output = tmp_path / "graph.json"
        export_graph(db, workspace_id=workspace_id, output_path=output)

        data = json.loads(output.read_text())
        concept_nodes = [n for n in data["nodes"] if n["type"] not in ("project", "session")]
        for node in concept_nodes:
            assert "id" in node
            assert "label" in node
            assert "type" in node
            assert "properties" in node
