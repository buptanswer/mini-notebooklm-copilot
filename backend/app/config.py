"""
项目全局配置 — 使用 pydantic-settings 管理环境变量与路径

多 Provider 支持说明
─────────────────────────────────────────────────────────────────
本项目各 AI 服务可分别配置不同的 Provider：

  嵌入（Embedding）  ← 始终使用 DashScope text-embedding-v4（中文最佳）
  重排序（Rerank）   ← 始终使用 DashScope qwen3-rerank
  VLM（图片/表格）   ← 始终使用 DashScope（需多模态能力）
  问答（QA Chat）    ← 可通过 QA_BASE_URL + QA_API_KEY 切换至任意
                       OpenAI 兼容 Provider（DeepSeek、Moonshot、OpenAI 等）

切换 QA 模型到 DeepSeek 示例（.env）：
  QA_BASE_URL=https://api.deepseek.com/v1
  QA_API_KEY=sk-xxxxxxxx
  QA_MODEL=deepseek-chat
  # 关闭 thinking（DeepSeek-chat 不支持；若用 deepseek-reasoner 可保持 false，
  # reasoner 模型会自动在 reasoning_content 字段返回思维链）
  QA_ENABLE_THINKING=false

切换 QA 模型到 OpenAI 示例（.env）：
  QA_BASE_URL=https://api.openai.com/v1
  QA_API_KEY=sk-xxxxxxxx
  QA_MODEL=gpt-4o

不设置 QA_BASE_URL / QA_API_KEY 时，自动回落到 DashScope。
─────────────────────────────────────────────────────────────────
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

    # ── 阿里云百炼 (DashScope) — 嵌入 / 重排序 / VLM ─────
    # 申请地址：https://bailian.console.aliyun.com
    dashscope_api_key: str = Field(default="", validation_alias="ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # ── 嵌入与重排序模型（固定使用 DashScope）────────────
    embedding_model: str = "text-embedding-v4"   # 1024 维，中英文最佳
    rerank_model: str = "qwen3-rerank"

    # ── VLM 模型（图片描述 / 表格摘要，固定使用 DashScope）
    # 注：若模型已更新，请在 .env 中设置 VLM_MODEL=新模型名
    vlm_model: str = Field(default="qwen-vl-plus", validation_alias="VLM_MODEL")

    # ── QA 问答模型（支持多 Provider，见文件头说明）────────
    # 默认使用 DashScope；可通过 QA_BASE_URL + QA_API_KEY 切换
    # 注：若 DashScope 模型名已更新，请在 .env 中设置 QA_MODEL=新模型名
    qa_model: str = Field(default="qwen-plus", validation_alias="QA_MODEL")
    qa_base_url: str = Field(default="", validation_alias="QA_BASE_URL")
    qa_api_key: str = Field(default="", validation_alias="QA_API_KEY")
    # 是否开启思维链（仅对 qwen3/deepseek-reasoner 等支持该功能的模型有效）
    qa_enable_thinking: bool = Field(default=False, validation_alias="QA_ENABLE_THINKING")

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

    # ── 解析并发 ──────────────────────────────────────────
    # 同时运行的解析流水线上限：批量重解析时避免 N 路并发打爆 MinerU/OSS/DashScope 连接
    max_concurrent_parses: int = Field(default=2, validation_alias="MAX_CONCURRENT_PARSES")

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

    @property
    def effective_qa_base_url(self) -> str:
        """QA 服务实际使用的 base_url。未配置时回落到 DashScope。"""
        return self.qa_base_url.rstrip("/") or self.dashscope_base_url.rstrip("/")

    @property
    def effective_qa_api_key(self) -> str:
        """QA 服务实际使用的 API Key。未配置时回落到 DashScope Key。"""
        return self.qa_api_key or self.dashscope_api_key

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
