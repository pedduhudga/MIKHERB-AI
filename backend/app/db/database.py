from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def migrate_legacy_unowned_projects(db, default_owner_uid: str = "legacy_migrated_owner") -> int:
    """
    Migration helper: Backfills null owner_uid on legacy projects so that owner_uid
    can be transitioned to nullable=False in database schema.
    """
    from app.models.models import Project
    count = db.query(Project).filter(Project.owner_uid.is_(None)).update(
        {Project.owner_uid: default_owner_uid},
        synchronize_session=False
    )
    db.commit()
    return count

