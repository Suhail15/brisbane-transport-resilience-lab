from dataclasses import dataclass
from pathlib import Path
import os

@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("RESILIENCE_DATA_DIR", "data"))
    database_url: str = os.getenv("DATABASE_URL", "postgresql://resilience:local-development@127.0.0.1:55432/resilience")
    broker: str = os.getenv("REDPANDA_BROKERS", "127.0.0.1:19092")
    timezone: str = "Australia/Brisbane"
    freshness_seconds: int = 120

settings = Settings()
