"""Environment-driven settings. Nothing secret has a default; nothing secret is committed."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("ATLAS_DATA_DIR", REPO_ROOT / "data")))
    # Providers. In privacy mode every provider is forced to its offline implementation.
    privacy_mode: bool = field(default_factory=lambda: _bool("ATLAS_PRIVACY_MODE"))
    geocoder: str = field(default_factory=lambda: os.environ.get("ATLAS_GEOCODER", "gazetteer"))       # gazetteer | nominatim
    vision: str = field(default_factory=lambda: os.environ.get("ATLAS_VISION", "heuristic"))           # heuristic | claude
    transcriber: str = field(default_factory=lambda: os.environ.get("ATLAS_TRANSCRIBER", "sidecar"))   # sidecar | whisper
    narrator: str = field(default_factory=lambda: os.environ.get("ATLAS_NARRATOR", "deterministic"))   # deterministic | claude
    nominatim_url: str = field(default_factory=lambda: os.environ.get("ATLAS_NOMINATIM_URL", "https://nominatim.openstreetmap.org"))
    nominatim_user_agent: str = field(default_factory=lambda: os.environ.get("ATLAS_NOMINATIM_USER_AGENT", ""))
    anthropic_api_key: str | None = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY") or None)
    llm_model: str = field(default_factory=lambda: os.environ.get("ATLAS_LLM_MODEL", "claude-sonnet-5-5"))
    # Server
    public_base_url: str = field(default_factory=lambda: os.environ.get("ATLAS_PUBLIC_BASE_URL", "http://localhost:8000"))
    web_base_url: str = field(default_factory=lambda: os.environ.get("ATLAS_WEB_BASE_URL", "http://localhost:3000"))
    cors_origins: str = field(default_factory=lambda: os.environ.get("ATLAS_CORS_ORIGINS", "http://localhost:3000,http://localhost:8081,http://127.0.0.1:3000,http://127.0.0.1:8081"))
    session_days: int = field(default_factory=lambda: int(os.environ.get("ATLAS_SESSION_DAYS", "60")))
    max_upload_mb: int = field(default_factory=lambda: int(os.environ.get("ATLAS_MAX_UPLOAD_MB", "200")))
    max_image_pixels: int = field(default_factory=lambda: int(os.environ.get("ATLAS_MAX_IMAGE_PIXELS", str(120_000_000))))
    workers: int = field(default_factory=lambda: int(os.environ.get("ATLAS_WORKERS", str(max(1, (os.cpu_count() or 2) - 1)))))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "atlas.sqlite3"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    def effective(self, provider: str) -> str:
        """Provider choice after privacy mode is applied."""
        offline = {"geocoder": "gazetteer", "vision": "heuristic", "transcriber": "sidecar", "narrator": "deterministic"}
        return offline[provider] if self.privacy_mode else getattr(self, provider)


@lru_cache
def get_settings() -> Settings:
    return Settings()
