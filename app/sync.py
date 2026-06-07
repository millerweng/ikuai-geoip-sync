from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from .cn_regions import group_label_for
from .ikuai_client import IKuaiClient
from .ip_fetcher import chunk_cidrs, code_to_name, fetch_city_cidrs
from .lookup import save_snapshot

log = logging.getLogger(__name__)


@dataclass
class CityResult:
    code: str
    name: str
    cidr_count: int
    group_count: int
    groups: list[str]
    error: str | None = None


@dataclass
class SyncResult:
    started_at: str
    finished_at: str
    cities: list[CityResult]
    ok: bool


def _build_group_base(code: str, group_prefix: str) -> str:
    """构造分组名前缀（不含拆分编号）。例如 "GEO_辽宁_大连" 或 "GEO_辽宁"。"""
    label = group_label_for(code)
    return f"{group_prefix}{label}" if group_prefix else label


def sync_cities(
    client: IKuaiClient,
    city_codes: list[str],
    max_per_group: int = 1000,
    group_prefix: str = "GEO_",
) -> SyncResult:
    started = datetime.now(timezone.utc).isoformat()
    results: list[CityResult] = []
    overall_ok = True
    snapshot_groups: dict[str, list[str]] = {}

    # 一次性清理本次配置下所有 GEO_ 前缀的旧分组（不依赖单一 base 名），
    # 防止用户改动选择/命名规则后留下僵尸分组。
    if group_prefix:
        try:
            removed = client.del_groups_with_prefix(group_prefix)
            log.info("pre-clean: removed %d existing groups with prefix %r", removed, group_prefix)
        except Exception:
            log.exception("pre-clean failed (continuing)")

    for code in city_codes:
        name = code_to_name(code)
        try:
            cidrs = fetch_city_cidrs(code)
            chunks = chunk_cidrs(cidrs, max_per_group)
            base = _build_group_base(code, group_prefix)
            group_names: list[str] = []
            for idx, chunk in enumerate(chunks, start=1):
                gname = base if idx == 1 else f"{base}{idx}"
                client.add_ip_group(
                    gname,
                    ",".join(chunk),
                    comment=f"auto:{code}#{idx}",
                )
                group_names.append(gname)
                snapshot_groups[gname] = chunk
            results.append(
                CityResult(code, name, len(cidrs), len(group_names), group_names)
            )
            log.info(
                "synced %s(%s) as base=%r: %d cidrs -> %d groups",
                name, code, base, len(cidrs), len(group_names),
            )
        except Exception as e:
            overall_ok = False
            log.exception("sync %s failed", code)
            results.append(CityResult(code, name, 0, 0, [], error=str(e)))

    finished = datetime.now(timezone.utc).isoformat()
    if snapshot_groups:
        save_snapshot(
            snapshot_groups,
            meta={
                "synced_at": finished,
                "city_codes": city_codes,
                "ok": overall_ok,
            },
        )
    return SyncResult(started_at=started, finished_at=finished, cities=results, ok=overall_ok)
