"""
项目全局配置 — 使用 pydantic-settings 管理环境变量与路径
"""

from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── 项目根目录 ──────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # mini-notebooklm/
BACKEND_ROOT = PROJECT_ROOT / "backend"
DATA_ROOT = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    """从 .env 或环境变量读取配置"""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── MinerU API ────────────────────────────────────────
    mineru_api_key: str = Field(default="", validation_alias="MINERU_API_KEY")
    mineru_api_base: str = "https://mineru.net/api/v4"
    mineru_model_version: str = "vlm"

    # ── 阿里云百炼 (DashScope) ─────────────────────────────
    # 优先读系统环境变量 ALIBABA_CLOUD_ACCESS_KEY_SECRET
    dashscope_api_key: str = Field(default="", validation_alias="ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # ── 模型名称 ──────────────────────────────────────────
    embedding_model: str = "text-embedding-v4"
    rerank_model: str = "qwen3-rerank"
    vlm_model: str = "qwen3.5-flash"
    qa_model: str = "qwen3.5-plus"

    # ── 数据路径 ──────────────────────────────────────────
    upload_dir: Path = DATA_ROOT / "uploads"
    mineru_zip_dir: Path = DATA_ROOT / "mineru_zips"
    rag_output_dir: Path = DATA_ROOT / "rag_output"
    sqlite_path: Path = DATA_ROOT / "sqlite" / "mini_notebooklm.db"
    qdrant_path: Path = DATA_ROOT / "qdrant_storage"

    # ── Qdrant ────────────────────────────────────────────
    qdrant_collection: str = "child_chunks"
    embedding_dim: int = 1024  # text-embedding-v4 维度

    # ── Chunking 参数 ─────────────────────────────────────
    child_chunk_min_tokens: int = 150
    child_chunk_max_tokens: int = 250
    child_chunk_overlap_ratio: float = 0.15

    # ── Server ────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True

    @field_validator("debug", mode="before")
    @classmethod
    def _coerce_debug_flag(cls, value):
        """兼容 DEBUG=release/dev 等字符串写法。"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            val = value.strip().lower()
            if val in {"1", "true", "yes", "on", "debug", "dev", "development"}:
                return True
            if val in {"0", "false", "no", "off", "release", "prod", "production"}:
                return False
        return bool(value)

    def ensure_dirs(self) -> None:
        """确保所有数据目录存在"""
        for d in [
            self.upload_dir,
            self.mineru_zip_dir,
            self.rag_output_dir,
            self.sqlite_path.parent,
            self.qdrant_path,
        ]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
