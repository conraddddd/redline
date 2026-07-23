"""Runner configuration, loaded from `.env` (or environment variables).

Uses pydantic-settings for the same reason Insight does: one typed,
validated source of truth instead of scattered os.environ calls, and a
single place to see every knob the runner exposes.

concurrency_limit=3 / request_timeout_s=90 are not arbitrary: an initial
run at 6/30 produced 30/66 timeouts, concentrated in jailbreak and the
more elaborate exfiltration attacks — i.e. missing data biased toward
exactly the categories where success is hardest to achieve, which would
have distorted per-category ASR. Insight's single embedded Qdrant client
and single-threaded local Ollama generation mean concurrency past ~2-3
doesn't add real throughput, just queueing — so lowering concurrency and
raising the timeout trades wall-clock time for completeness, which is the
right trade for a one-shot eval run.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    target_url: str = "http://localhost:8000/draft"
    concurrency_limit: int = 3
    request_timeout_s: float = 90.0
    retry_delay_s: float = 1.0


settings = Settings()
