"""Explicit deployment settings; never log credentials."""
from dataclasses import dataclass, field
import os
from pathlib import Path


def flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    db_path: str = "./data/vera.sqlite3"
    team_name: str = "Vera Compass"
    team_members: tuple[str, ...] = ("SET_YOUR_NAME",)
    contact_email: str = "SET_YOUR_EMAIL"
    submitted_at: str = "2026-09-27T00:00:00Z"
    api_token: str = field(default="", repr=False)
    admin_token: str = field(default="", repr=False)
    max_body_bytes: int = 512_000
    max_contexts: int = 10_000
    merchant_cooldown_seconds: int = 1800
    customer_cooldown_seconds: int = 86400
    retention_hours: float = 4
    max_turns: int = 12
    semantic_enabled: bool = False
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    llm_api_key: str = field(default="", repr=False)
    llm_timeout_seconds: float = 3.0
    llm_max_calls: int = 100
    allow_insecure_llm: bool = False
    public_studio: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls(
            db_path=os.getenv("VERA_DB_PATH", "./data/vera.sqlite3"),
            team_name=os.getenv("VERA_TEAM_NAME", "Vera Compass"),
            team_members=tuple(x.strip() for x in os.getenv("VERA_TEAM_MEMBERS", "SET_YOUR_NAME").split(",") if x.strip()),
            contact_email=os.getenv("VERA_CONTACT_EMAIL", "SET_YOUR_EMAIL"),
            submitted_at=os.getenv("VERA_SUBMITTED_AT", "2026-09-27T00:00:00Z"),
            api_token=os.getenv("VERA_API_TOKEN", ""),
            admin_token=os.getenv("VERA_ADMIN_TOKEN", ""),
            merchant_cooldown_seconds=int(os.getenv("VERA_MERCHANT_COOLDOWN", "1800")),
            customer_cooldown_seconds=int(os.getenv("VERA_CUSTOMER_COOLDOWN", "86400")),
            retention_hours=float(os.getenv("VERA_RETENTION_HOURS", "4")),
            semantic_enabled=flag("VERA_SEMANTIC_ENABLED"),
            llm_base_url=os.getenv("VERA_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            llm_model=os.getenv("VERA_LLM_MODEL", ""),
            llm_api_key=os.getenv("VERA_LLM_API_KEY", ""),
            llm_timeout_seconds=float(os.getenv("VERA_LLM_TIMEOUT", "3")),
            llm_max_calls=int(os.getenv("VERA_LLM_MAX_CALLS", "100")),
            allow_insecure_llm=flag("VERA_ALLOW_INSECURE_LLM"),
            public_studio=flag("VERA_PUBLIC_STUDIO"),
        )
        if s.retention_hours <= 0 or min(s.merchant_cooldown_seconds, s.customer_cooldown_seconds) < 0:
            raise ValueError("Retention must be positive; cooldowns cannot be negative")
        if not 0 < s.llm_timeout_seconds <= 5 or s.llm_max_calls < 0:
            raise ValueError("LLM timeout must be (0,5] seconds; call budget must be nonnegative")
        if s.semantic_enabled and not (s.llm_model and s.llm_api_key):
            raise ValueError("Semantic mode requires VERA_LLM_MODEL and VERA_LLM_API_KEY")
        if s.semantic_enabled and not s.llm_base_url.startswith("https://") and not s.allow_insecure_llm:
            raise ValueError("LLM endpoint must use HTTPS (local tests may explicitly opt out)")
        return s

    def ensure_parent(self) -> None:
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
