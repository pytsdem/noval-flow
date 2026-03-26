from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "novel-flow"
    database_path: Path = Field(default=Path("data/novel_flow.db"))
    doubao_api_key: str | None = None
    doubao_model: str | None = None
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, database_path: str | None = None) -> "Settings":
        import os

        db_value: str | None = database_path or os.getenv("NOVEL_FLOW_DB")
        return cls(
            database_path=Path(db_value) if db_value else Path("data/novel_flow.db"),
            doubao_api_key=os.getenv("DOUBAO_API_KEY"),
            doubao_model=os.getenv("DOUBAO_MODEL"),
            doubao_base_url=os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
            log_level=os.getenv("NOVEL_FLOW_LOG_LEVEL", "INFO"),
        )
