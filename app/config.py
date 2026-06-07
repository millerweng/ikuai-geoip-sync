from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
CONFIG_FILE = DATA_DIR / "config.json"


@dataclass
class AppConfig:
    ikuai_url: str = "http://10.0.0.1"
    ikuai_user: str = "admin"
    ikuai_pass: str = ""
    city_codes: list[str] = field(default_factory=lambda: ["210200"])
    max_per_group: int = 1000
    group_prefix: str = "GEO_"
    sync_cron: str = "0 4 11 * *"

    def public_dict(self) -> dict:
        d = asdict(self)
        d["ikuai_pass"] = "***" if self.ikuai_pass else ""
        return d


def _from_env() -> AppConfig:
    return AppConfig(
        ikuai_url=os.getenv("IKUAI_URL", "http://10.0.0.1"),
        ikuai_user=os.getenv("IKUAI_USER", "admin"),
        ikuai_pass=os.getenv("IKUAI_PASS", ""),
        city_codes=[c.strip() for c in os.getenv("CITY_CODES", "210200").split(",") if c.strip()],
        max_per_group=int(os.getenv("MAX_PER_GROUP", "1000")),
        group_prefix=os.getenv("GROUP_PREFIX", "GEO_"),
        sync_cron=os.getenv("SYNC_CRON", "0 4 11 * *"),
    )


class ConfigStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cfg: AppConfig = _from_env()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text())
                self._cfg = self._merge(self._cfg, data)
                log.info("loaded config from %s", CONFIG_FILE)
            except Exception:
                log.exception("failed to load config.json, falling back to env")

    @staticmethod
    def _merge(base: AppConfig, patch: dict) -> AppConfig:
        valid_keys = {f.name for f in fields(AppConfig)}
        clean = {k: v for k, v in patch.items() if k in valid_keys and v is not None}
        merged = asdict(base)
        merged.update(clean)
        if "city_codes" in clean and isinstance(clean["city_codes"], str):
            merged["city_codes"] = [c.strip() for c in clean["city_codes"].split(",") if c.strip()]
        return AppConfig(**merged)

    def get(self) -> AppConfig:
        with self._lock:
            return AppConfig(**asdict(self._cfg))

    def update(self, patch: dict) -> AppConfig:
        with self._lock:
            new_cfg = self._merge(self._cfg, patch)
            CONFIG_FILE.write_text(
                json.dumps(asdict(new_cfg), ensure_ascii=False, indent=2)
            )
            self._cfg = new_cfg
            log.info("config updated, persisted to %s", CONFIG_FILE)
            return AppConfig(**asdict(new_cfg))


store = ConfigStore()
