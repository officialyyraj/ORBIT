from app.db.session import Base, SessionLocal, engine
from app.db import models  # noqa: F401
from app.kst.seed_data import connect_legacy_topics, seed
from app.content import upgrade_content_schema, import_library
from app.content_library import build_library

if __name__ == '__main__':
    upgrade_content_schema(engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
        result = import_library(db, build_library())
        connect_legacy_topics(db)
        print(f"ORBIT content import: {result}")
        print('ORBIT seed complete')
    finally:
        db.close()
