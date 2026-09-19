"""Settings and thresholds. The only place that reads .env or holds a tuned number."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Values from .env. Secrets are read here and never logged or echoed."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deepgram_api_key: str = ""
    deepgram_model: str = "nova-3"
    deepgram_language: str = "en-AU"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    llm_enabled: bool = False

    db_path: Path = PROJECT_ROOT / "data" / "app.db"
    audio_dir: Path = PROJECT_ROOT / "data" / "recordings"
    cache_dir: Path = PROJECT_ROOT / "cache"
    # The script that was actually read on the demo call, used to recover speaker
    # turns when diarization returns a single speaker (DECISIONS D18).
    recorded_script_path: Path = PROJECT_ROOT / "data" / "scripts" / "recorded_script.md"

    qa_sample_percent: int = Field(default=5, ge=0, le=100)

    @property
    def database_url(self) -> str:
        return f"sqlite+pysqlite:///{self.db_path}"

    def ensure_dirs(self) -> None:
        """Create the local data and cache directories. All are gitignored."""
        for directory in (self.db_path.parent, self.audio_dir, self.cache_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Thresholds. Settled in the rehearsal spike, see PLAN.md Reference. Never inline these.

# Type A verbatim matching, rapidfuzz score out of 100.
VERBATIM_PASS_THRESHOLD = 88
VERBATIM_REVIEW_THRESHOLD = 72

# Below this average transcription confidence a PASS or FAIL is downgraded to REVIEW.
LOW_STT_CONFIDENCE = 0.75

# Type B factual comparisons.
RATE_TOLERANCE_C_PER_KWH = 0.05

# Speaker attribution when diarization returns one speaker (DECISIONS D18).
# Below this rapidfuzz score a turn's speaker is unknown, not guessed.
SPEAKER_MATCH_MIN_SCORE = 70.0
# An unknown speaker caps the turn's confidence, so a critical check that leans
# on it routes to REVIEW instead of PASS (hard rule 7).
UNKNOWN_SPEAKER_CONFIDENCE = 0.5

# Type C behaviour notes, seconds.
DEAD_AIR_THRESHOLD_S = 20.0
INTERRUPTION_OVERLAP_S = 1.0
