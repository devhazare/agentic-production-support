"""
core/config/settings.py
-----------------------
Single source of truth for all configuration.
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class AppMode(str, Enum):
    MOCK = "mock"
    LIVE = "live"


class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"


class VectorStore(str, Enum):
    FAISS = "faiss"
    OPENSEARCH = "opensearch"
    CHROMA = "chroma"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    # ── Project ────────────────────────────────────────────────────────────
    project_name: str = "Agentic Support Framework"
    environment: Environment = Environment.DEVELOPMENT
    app_mode: AppMode = AppMode.MOCK
    log_level: str = "INFO"
    debug: bool = False

    # ── API ────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_v1_prefix: str = "/api/v1"
    api_request_timeout_sec: int = 30

    # ── LLM ────────────────────────────────────────────────────────────────
    llm_provider: LLMProvider = LLMProvider.OLLAMA
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-6"
    llm_temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    llm_max_tokens: int = Field(default=1000, gt=0)
    llm_timeout_sec: int = 120

    # ── Embeddings ────────────────────────────────────────────────────────
    embed_model: str = "all-MiniLM-L6-v2"
    embed_device: str = "cpu"
    embed_batch_size: int = 32

    # ── Vector store ──────────────────────────────────────────────────────
    vector_store: VectorStore = VectorStore.FAISS
    faiss_index_path: Path = Path("./data/faiss_index")
    knowledge_base_path: Path = Path("./data/knowledge_base")
    rag_top_k: int = 4
    # FAISS L2 distances for all-MiniLM-L6-v2 are typically 0.0–2.0 for strong
    # matches. Keep threshold high (100) so retriever returns top_k results
    # unfiltered; filter by semantic rank instead.
    rag_similarity_threshold: float = 100.0

    # ── AWS operational intelligence MVP ─────────────────────────────────
    use_aws: bool = False
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    bedrock_max_tokens: int = 1200
    bedrock_temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    opensearch_endpoint: str | None = None
    opensearch_index: str = "incident-knowledge"
    s3_bucket_name: str = "ai-ops-knowledge-mvp"
    dynamodb_incidents_table: str = "ai-ops-incidents-mvp"
    dynamodb_audit_table: str = "ai-ops-audit-mvp"
    remediation_lambda_name: str = "ai-ops-mock-remediation-mvp"
    local_data_dir: Path = Path("./sample_data")
    local_store_path: Path = Path("./.local/incident_store.json")
    local_audit_path: Path = Path("./.local/audit_log.jsonl")
    min_grounded_citations: int = 1
    confidence_review_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    auto_mock_confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    pii_scrub_replacement: str = "[REDACTED]"
    model_egress_sanitization_enabled: bool = True
    model_egress_fail_closed: bool = True
    model_egress_redaction_token: str = "[MODEL_REDACTED]"

    # ── Log sources ───────────────────────────────────────────────────────
    # Set to an exact file path, or "disabled" to skip that source.
    # POC example:  PYTHON_LOG_PATH=../sample_app/logs/app.log
    magento_log_path: str = "disabled"
    magento_exception_log_path: str = "disabled"
    magento_system_log_path: str = "disabled"
    magento_access_log_path: str = "disabled"
    magento_failure_threshold_count: int = 5
    magento_failure_window_seconds: int = 300
    magento_incident_cooldown_seconds: int = 60
    aem_log_path: str = "disabled"
    java_log_path: str = "disabled"
    python_log_path: str = "disabled"
    log_poll_interval_sec: int = 5

    # ── Incident persistence ─────────────────────────────────────────────
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "agentic_support"
    mongodb_incidents_collection: str = "incidents"
    mongodb_enabled: bool = True

    # ── Agent config ──────────────────────────────────────────────────────
    auto_remediation_enabled: bool = True
    human_approval_required_severity: list[str] = Field(default=["CRITICAL"])
    max_pipeline_retries: int = 3
    pipeline_timeout_sec: int = 300

    # ── Alerting ──────────────────────────────────────────────────────────
    slack_bot_token: SecretStr | None = None
    slack_incidents_channel: str = "#incidents"
    slack_oncall_channel: str = "#oncall"
    jira_base_url: str | None = None
    jira_api_token: SecretStr | None = None
    jira_project_key: str = "SRE"

    @field_validator("faiss_index_path", "knowledge_base_path", "local_data_dir", "local_store_path", "local_audit_path", mode="before")
    @classmethod
    def coerce_path(cls, v: str | Path) -> Path:
        return Path(v)

    @property
    def is_mock(self) -> bool:
        return self.app_mode == AppMode.MOCK

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton Settings. Use as FastAPI dependency."""
    return Settings()
