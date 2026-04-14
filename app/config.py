from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_sqlite_url() -> str:
    db_path = (Path(__file__).resolve().parent.parent / "data" / "plant_extreme.db").as_posix()
    return f"sqlite:///{db_path}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLANT_", extra="ignore")

    database_url: str = _default_sqlite_url()
    seeds_dir: Path = Path(__file__).resolve().parent.parent / "seeds"


settings = Settings()
