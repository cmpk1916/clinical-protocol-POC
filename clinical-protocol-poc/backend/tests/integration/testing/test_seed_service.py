from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from protocol_poc.db import Base
from protocol_poc.files.service import LocalFileStorage
from protocol_poc.studies.models import Fact, Study
from protocol_poc.testing.seed_service import seed_synthetic_study


def test_seed_service_inserts_foreign_key_parents_before_children(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        command = seed_synthetic_study(
            session,
            LocalFileStorage(tmp_path),
            "synthetic-phase-2",
            "happy_path",
        )
        session.commit()

        assert session.scalar(select(Study).where(Study.id == "synthetic-phase-2"))
        assert session.scalar(select(Fact).where(Fact.id == "fact-dose"))
        assert command["templateVersionId"] == "template-v1"
