from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class IKuaiError(RuntimeError):
    pass


class IKuaiClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self._logged_in = False

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "IKuaiClient":
        self.login()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def login(self) -> None:
        passwd_md5 = hashlib.md5(self.password.encode()).hexdigest()
        pass_b64 = base64.b64encode(("salt_11" + self.password).encode()).decode()
        r = self._client.post(
            "/Action/login",
            json={
                "username": self.username,
                "passwd": passwd_md5,
                "pass": pass_b64,
                "remember_password": "",
            },
        )
        r.raise_for_status()
        data = r.json()
        if data.get("Result") != 10000:
            raise IKuaiError(f"login failed: {data}")
        self._logged_in = True
        log.info("ikuai login ok")

    def call(self, func_name: str, action: str, param: dict[str, Any]) -> dict[str, Any]:
        if not self._logged_in:
            self.login()
        r = self._client.post(
            "/Action/call",
            json={"func_name": func_name, "action": action, "param": param},
        )
        r.raise_for_status()
        data = r.json()
        if data.get("Result") not in (30000, 10000):
            raise IKuaiError(f"{func_name}.{action} failed: {data}")
        return data

    def list_ip_groups(self) -> list[dict[str, Any]]:
        data = self.call(
            "ipgroup",
            "show",
            {"TYPE": "data,total", "limit": "0,1000", "ORDER_BY": "", "ORDER": ""},
        )
        return data.get("Data", {}).get("data", []) or []

    def add_ip_group(self, group_name: str, addr_pool: str, comment: str = "") -> int:
        data = self.call(
            "ipgroup",
            "add",
            {"group_name": group_name, "addr_pool": addr_pool, "type": 0, "comment": comment},
        )
        return int(data.get("RowId", 0))

    def del_ip_group(self, group_id: int) -> None:
        self.call("ipgroup", "del", {"id": group_id})

    def upsert_ip_group(self, group_name: str, addr_pool: str, comment: str = "") -> int:
        for g in self.list_ip_groups():
            if g.get("group_name") == group_name:
                self.del_ip_group(int(g["id"]))
                break
        return self.add_ip_group(group_name, addr_pool, comment)

    def del_groups_with_prefix(self, prefix: str) -> int:
        count = 0
        for g in self.list_ip_groups():
            if str(g.get("group_name", "")).startswith(prefix):
                self.del_ip_group(int(g["id"]))
                count += 1
        return count
