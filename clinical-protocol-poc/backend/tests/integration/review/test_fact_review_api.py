from fastapi.testclient import TestClient

from protocol_poc.app import create_app
from protocol_poc.config import get_settings
from protocol_poc.db import Base
from protocol_poc.studies.models import Fact, FactVersion, Study


def test_review_queue_orders_blockers_before_critical_and_low_confidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'review.db'}")
    monkeypatch.setenv("ALLOW_INSECURE_IDENTITY_HEADERS", "true")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as session:
        session.add(Study(id="study-a", tenant_id="tenant-a", name="Synthetic study"))
        session.flush()
        facts = [
            Fact(id="low", tenant_id="tenant-a", study_id="study-a", kind="population", status="candidate"),
            Fact(id="critical", tenant_id="tenant-a", study_id="study-a", kind="dose", status="candidate", critical=True),
            Fact(id="conflict", tenant_id="tenant-a", study_id="study-a", kind="dose", status="conflicted", critical=True),
        ]
        session.add_all(facts)
        session.flush()
        session.add_all([
            FactVersion(tenant_id="tenant-a", fact_id="low", version=1, value_json={"confidence": 0.2}, is_current=True),
            FactVersion(tenant_id="tenant-a", fact_id="critical", version=1, value_json={"confidence": 0.9}, is_current=True),
            FactVersion(tenant_id="tenant-a", fact_id="conflict", version=1, value_json={"confidence": 0.8}, is_current=True),
        ])
        session.commit()

    response = TestClient(app).get(
        "/api/studies/study-a/fact-review",
        headers={"X-Tenant-ID": "tenant-a", "X-Actor-ID": "writer-a"},
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["conflict", "critical", "low"]
    get_settings.cache_clear()
