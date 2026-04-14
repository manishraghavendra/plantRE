from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _sqlite_pragma(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine():
    connect_args: dict = {}
    if settings.database_url.startswith("sqlite"):
        raw_path = settings.database_url.removeprefix("sqlite:///")
        Path(raw_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        connect_args["check_same_thread"] = False
    eng = create_engine(settings.database_url, echo=False, connect_args=connect_args)
    if settings.database_url.startswith("sqlite"):
        event.listen(eng, "connect", _sqlite_pragma)
    return eng


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def run_migrations():
    migration_path = Path(__file__).resolve().parent.parent / "migrations" / "001_initial.sql"
    sql = migration_path.read_text(encoding="utf-8")
    # SQLite driver rejects multi-statement SQL in a single execute(); use executescript.
    raw = engine.raw_connection()
    try:
        raw.executescript(sql)
        raw.commit()
    finally:
        raw.close()


def ensure_growing_profile_climate_context_column():
    with engine.connect() as c:
        row = c.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='growing_profile'")
        ).fetchone()
        if row is None:
            return
        cols = c.execute(text("PRAGMA table_info(growing_profile)")).fetchall()
    names = [r[1] for r in cols]
    if "climate_context" not in names:
        with engine.begin() as c:
            c.execute(text("ALTER TABLE growing_profile ADD COLUMN climate_context TEXT"))


def ensure_hazard_kind_column():
    with engine.connect() as c:
        row = c.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='hazard'")
        ).fetchone()
        if row is None:
            return
        cols = c.execute(text("PRAGMA table_info(hazard)")).fetchall()
    names = [r[1] for r in cols]
    if "kind" not in names:
        with engine.begin() as c:
            c.execute(
                text(
                    "ALTER TABLE hazard ADD COLUMN kind TEXT NOT NULL DEFAULT 'food_safety'"
                )
            )


def ensure_plant_image_url_column():
    with engine.connect() as c:
        row = c.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='plant'")
        ).fetchone()
        if row is None:
            return
        cols = c.execute(text("PRAGMA table_info(plant)")).fetchall()
    names = [r[1] for r in cols]
    if "image_url" not in names:
        with engine.begin() as c:
            c.execute(text("ALTER TABLE plant ADD COLUMN image_url TEXT"))


def init_db():
    with engine.connect() as c:
        row = c.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='plant_type'")
        ).fetchone()
    if row is None:
        run_migrations()
    ensure_plant_image_url_column()
    ensure_growing_profile_climate_context_column()
    ensure_hazard_kind_column()
    uploads = Path(__file__).resolve().parent / "static" / "uploads" / "plants"
    uploads.mkdir(parents=True, exist_ok=True)
