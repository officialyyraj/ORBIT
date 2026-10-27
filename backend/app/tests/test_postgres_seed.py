import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.content import import_library
from app.content_library import build_library
from app.db.models import Base, Module, Topic, Track
from app.kst.seed_data import connect_legacy_topics, seed


@pytest.mark.skipif(
    not os.getenv('ORBIT_TEST_POSTGRES_URL'),
    reason='ORBIT_TEST_POSTGRES_URL must point to a disposable PostgreSQL database',
)
def test_postgres_seed_succeeds_twice_in_a_fresh_schema():
    database_url = os.environ['ORBIT_TEST_POSTGRES_URL']
    admin_engine = create_engine(database_url)
    schema = f'orbit_seed_test_{uuid4().hex}'
    engine = None
    try:
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')

        engine = create_engine(
            database_url,
            connect_args={'options': f'-csearch_path={schema}'},
        )
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)

        with Session() as db:
            data = build_library()
            counts = []
            for _ in range(2):
                seed(db)
                import_library(db, data)
                connect_legacy_topics(db)
                counts.append((
                    db.scalar(select(func.count()).select_from(Track)),
                    db.scalar(select(func.count()).select_from(Module)),
                    db.scalar(select(func.count()).select_from(Topic)),
                ))

            assert counts[0] == counts[1]
            assert db.scalar(
                select(func.count())
                .select_from(Topic)
                .outerjoin(Module, Topic.module_id == Module.id)
                .where(Topic.module_id.is_not(None), Module.id.is_(None))
            ) == 0
            assert db.scalar(
                select(func.count())
                .select_from(Module)
                .outerjoin(Track, Module.track_id == Track.id)
                .where(Track.id.is_(None))
            ) == 0
    finally:
        if engine is not None:
            engine.dispose()
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        admin_engine.dispose()
