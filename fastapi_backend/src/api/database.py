import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# PUBLIC_INTERFACE
def get_database_url() -> str:
    """Return SQLAlchemy DB URL assembled from environment variables.

    Expected env vars (set via .env):
    - MYSQL_URL: Full SQLAlchemy URL overrides individual pieces if present.
    - MYSQL_USER
    - MYSQL_PASSWORD
    - MYSQL_DB
    - MYSQL_PORT
    - MYSQL_HOST (optional, defaults to 'localhost')

    Note: Do not hardcode secrets here. Ensure orchestrator sets env variables.
    """
    url = os.getenv("MYSQL_URL")
    if url:
        return url

    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")
    db = os.getenv("MYSQL_DB")
    port = os.getenv("MYSQL_PORT", "3306")
    host = os.getenv("MYSQL_HOST", "localhost")

    # Use PyMySQL driver
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}"


DATABASE_URL = get_database_url()

# Create engine and session factory
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# PUBLIC_INTERFACE
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and ensures closing."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
