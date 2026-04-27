from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "novel-flow"
    database_path: Path = Field(default=Path("data/novel_flow.db"))
    llm_provider: str = "deepseek"
    doubao_api_key: str | None = None
    doubao_model: str | None = None
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    deepseek_api_key: str | None = None
    deepseek_model: str | None = "deepseek-v4-pro"
    deepseek_base_url: str = "https://api.deepseek.com"
    openai_api_key: str | None = None
    openai_model: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    codex_exe: str = "codex"
    codex_model: str | None = None
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, database_path: str | None = None) -> "Settings":
        import os

        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            cls._load_dotenv_fallback()

        db_value: str | None = database_path or os.getenv("NOVEL_FLOW_DB")
        return cls(
            database_path=Path(db_value) if db_value else Path("data/novel_flow.db"),
            llm_provider=os.getenv("LLM_PROVIDER", "deepseek"),
            doubao_api_key=os.getenv("DOUBAO_API_KEY"),
            doubao_model=os.getenv("DOUBAO_MODEL"),
            doubao_base_url=os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL"),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            codex_exe=os.getenv("CODEX_EXE", "codex"),
            codex_model=os.getenv("CODEX_MODEL") or None,
            log_level=os.getenv("NOVEL_FLOW_LOG_LEVEL", "INFO"),
        )

    @staticmethod
    def _load_dotenv_fallback() -> None:
        import os

        env_path = Path(__file__).resolve().parents[2] / ".env"
        if not env_path.exists():
            return

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            value = value.strip().strip('"').strip("'")
            os.environ[key] = value
