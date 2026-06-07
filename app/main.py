from __future__ import annotations

import dataclasses
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles

from .config import store as cfg_store
from .cn_regions import PROVINCES, CODE_TO_NAME
from .ikuai_client import IKuaiClient
from .ip_fetcher import code_to_name
from .lookup import load_snapshot, lookup as lookup_ip
from .sync import CityResult, SyncResult, sync_cities

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("ikuai-geoip-sync")

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "state.json"
LOG_FILE = DATA_DIR / "sync.log"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()

_run_lock = Lock()
_last_result: SyncResult | None = None
scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def require_token(authorization: str | None = Header(default=None)) -> None:
    if not ADMIN_TOKEN:
        return
    expected = f"Bearer {ADMIN_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid or missing token")


def _load_state() -> None:
    global _last_result
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            cities = [CityResult(**c) for c in data.get("cities", [])]
            _last_result = SyncResult(
                started_at=data["started_at"],
                finished_at=data["finished_at"],
                cities=cities,
                ok=data["ok"],
            )
        except Exception:
            log.exception("failed to load state")


def _save_state(result: SyncResult) -> None:
    STATE_FILE.write_text(json.dumps(dataclasses.asdict(result), ensure_ascii=False, indent=2))


def _append_log(line: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a") as f:
        f.write(f"[{ts}] {line}\n")


def run_sync(city_codes: list[str] | None = None) -> SyncResult:
    global _last_result
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="another sync is in progress")
    try:
        cfg = cfg_store.get()
        if not cfg.ikuai_pass:
            raise HTTPException(status_code=400, detail="iKuai password not configured")
        codes = city_codes or cfg.city_codes
        _append_log(f"sync start, cities={codes}")
        with IKuaiClient(cfg.ikuai_url, cfg.ikuai_user, cfg.ikuai_pass) as client:
            result = sync_cities(client, codes, cfg.max_per_group, cfg.group_prefix)
        _last_result = result
        _save_state(result)
        for c in result.cities:
            _append_log(f"  {c.name}({c.code}): {c.cidr_count} cidrs -> {c.group_count} groups{' ERROR: '+c.error if c.error else ''}")
        _append_log(f"sync done, ok={result.ok}")
        return result
    finally:
        _run_lock.release()


def _scheduled_sync() -> None:
    try:
        run_sync()
    except Exception:
        log.exception("scheduled sync failed")


def _reschedule(cron_expr: str) -> None:
    if scheduler.get_job("sync"):
        scheduler.remove_job("sync")
    scheduler.add_job(
        _scheduled_sync,
        CronTrigger.from_crontab(cron_expr, timezone="Asia/Shanghai"),
        id="sync",
    )
    job = scheduler.get_job("sync")
    next_run = getattr(job, "next_run_time", None) if job else None
    log.info("scheduled with cron=%s, next=%s", cron_expr, next_run)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_state()
    load_snapshot()
    cfg = cfg_store.get()
    _reschedule(cfg.sync_cron)
    scheduler.start()
    log.info("scheduler started, cron=%s", cfg.sync_cron)
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="iKuai GeoIP Sync", lifespan=lifespan)


@app.get("/api/status")
def status() -> dict:
    cfg = cfg_store.get()
    job = scheduler.get_job("sync")
    next_run = getattr(job, "next_run_time", None) if job else None
    return {
        "config": cfg.public_dict(),
        "city_names": [code_to_name(c) for c in cfg.city_codes],
        "next_run": next_run.isoformat() if next_run else None,
        "last_result": dataclasses.asdict(_last_result) if _last_result else None,
        "running": _run_lock.locked(),
        "auth_required": bool(ADMIN_TOKEN),
    }


@app.get("/api/regions")
def list_regions() -> dict:
    """返回省/市树供前端选择器使用。"""
    return {"provinces": PROVINCES}


@app.post("/api/sync", dependencies=[Depends(require_token)])
def trigger_sync(payload: dict | None = None) -> dict:
    cities = (payload or {}).get("cities") if payload else None
    result = run_sync(cities)
    return dataclasses.asdict(result)


@app.get("/api/config")
def get_config() -> dict:
    return cfg_store.get().public_dict()


@app.put("/api/config", dependencies=[Depends(require_token)])
def update_config(patch: dict) -> dict:
    if "sync_cron" in patch and patch["sync_cron"]:
        try:
            CronTrigger.from_crontab(patch["sync_cron"], timezone="Asia/Shanghai")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid cron: {e}")
    if "ikuai_pass" in patch and patch["ikuai_pass"] in ("", None, "***"):
        patch.pop("ikuai_pass")
    new_cfg = cfg_store.update(patch)
    if "sync_cron" in patch:
        _reschedule(new_cfg.sync_cron)
    return new_cfg.public_dict()


@app.get("/api/cities")
def list_cities() -> dict:
    """legacy：返回扁平 code→name 映射（前端不再用，但保留兼容）"""
    cfg = cfg_store.get()
    return {"available": CODE_TO_NAME, "selected": cfg.city_codes}


@app.get("/api/lookup")
def api_lookup(ip: str) -> dict:
    return lookup_ip(ip)


@app.get("/api/logs")
def get_logs(tail: int = 200) -> dict:
    if not LOG_FILE.exists():
        return {"lines": []}
    lines = LOG_FILE.read_text().splitlines()
    return {"lines": lines[-tail:]}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
