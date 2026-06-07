from __future__ import annotations

import ipaddress
import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
SNAPSHOT_FILE = DATA_DIR / "snapshot.json"

_lock = threading.RLock()
_snapshot: dict[str, list[ipaddress.IPv4Network | ipaddress.IPv6Network]] = {}
_meta: dict = {}


def _parse_cidrs(items: list[str]) -> list:
    out = []
    for c in items:
        try:
            out.append(ipaddress.ip_network(c.strip(), strict=False))
        except ValueError:
            log.warning("invalid cidr %r ignored", c)
    return out


def save_snapshot(groups: dict[str, list[str]], meta: dict | None = None) -> None:
    """groups: {group_name: [cidr_str, ...]}"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta or {}, "groups": groups}
    SNAPSHOT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    with _lock:
        _snapshot.clear()
        _snapshot.update({g: _parse_cidrs(cs) for g, cs in groups.items()})
        _meta.clear()
        _meta.update(meta or {})
    log.info("snapshot saved: %d groups", len(groups))


def load_snapshot() -> None:
    if not SNAPSHOT_FILE.exists():
        return
    try:
        data = json.loads(SNAPSHOT_FILE.read_text())
        with _lock:
            _snapshot.clear()
            _snapshot.update(
                {g: _parse_cidrs(cs) for g, cs in data.get("groups", {}).items()}
            )
            _meta.clear()
            _meta.update(data.get("meta", {}))
        log.info("snapshot loaded: %d groups", len(_snapshot))
    except Exception:
        log.exception("failed to load snapshot")


def lookup(ip_str: str) -> dict:
    try:
        ip = ipaddress.ip_address(ip_str.strip())
    except ValueError as e:
        return {"ok": False, "error": f"invalid ip: {e}"}

    matches = []
    with _lock:
        for group, networks in _snapshot.items():
            for net in networks:
                if ip.version == net.version and ip in net:
                    matches.append({"group": group, "cidr": str(net)})
                    break
        meta = dict(_meta)
        total_groups = len(_snapshot)

    return {
        "ok": True,
        "ip": str(ip),
        "matches": matches,
        "in_any_group": bool(matches),
        "snapshot_groups": total_groups,
        "snapshot_meta": meta,
    }
