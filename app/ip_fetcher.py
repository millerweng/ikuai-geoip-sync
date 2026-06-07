from __future__ import annotations

import logging

import httpx

from .cn_regions import CODE_TO_NAME

log = logging.getLogger(__name__)

IPLIST_URL = "https://metowolf.github.io/iplist/data/cncity/{code}.txt"


def code_to_name(code: str) -> str:
    return CODE_TO_NAME.get(code, code)


def fetch_city_cidrs(code: str, timeout: float = 30.0) -> list[str]:
    url = IPLIST_URL.format(code=code)
    log.info("fetching %s", url)
    r = httpx.get(url, timeout=timeout)
    r.raise_for_status()
    cidrs = [ln.strip() for ln in r.text.splitlines() if ln.strip() and not ln.startswith("#")]
    log.info("region %s (%s): %d cidrs", code, code_to_name(code), len(cidrs))
    return cidrs


def chunk_cidrs(cidrs: list[str], max_per_group: int) -> list[list[str]]:
    return [cidrs[i : i + max_per_group] for i in range(0, len(cidrs), max_per_group)] or [[]]
