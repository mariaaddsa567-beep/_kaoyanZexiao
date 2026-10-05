# -*- coding: utf-8 -*-
"""HTTP 客户端：带 UA、重试与限速的会话封装。

合规说明：仅采集研招网/软科等站点的公开数据，限速 0.25s/请求（Pacer），
失败退避重试 ≤3 次。UA 保持浏览器形态为研招网 zsml 接口的硬性校验要求
（非浏览器 UA 直接 403），已通过限速降低对目标站点的影响。
"""
import threading
import time

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class Pacer:
    """跨线程共享的速率控制器（应对 IP 级滑动窗口限流）。"""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self):
        with self._lock:
            wait = self._last + self.min_interval - time.time()
            if wait > 0:
                time.sleep(wait)
                self._last = time.time()
            else:
                self._last = time.time()


class Http:
    def __init__(self, referer: str = "", min_interval: float = 0.25, timeout: int = 30,
                 retries: int = 3, pacer: Pacer | None = None):
        self.referer = referer
        self.pacer = pacer or Pacer(min_interval)
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": UA,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer,
        })
        self.timeout = timeout
        self.retries = retries
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def reset(self):
        """重建底层会话（应对会话级风控）。"""
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": UA,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.referer,
        })

    def _pace(self):
        self.pacer.wait()

    def get(self, url, **kw):
        return self._request("GET", url, **kw)

    def post(self, url, **kw):
        return self._request("POST", url, **kw)

    def _request(self, method, url, **kw):
        last_err = None
        for i in range(self.retries):
            self._pace()
            try:
                r = self.s.request(method, url, timeout=self.timeout, **kw)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"HTTP {r.status_code}")
                r.raise_for_status()
                return r
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(1.5 * (i + 1))
        raise RuntimeError(f"请求失败 {method} {url}: {last_err}")


def form_page(base: dict, start: int, page: int, size: int) -> dict:
    """研招网分页表单公共字段。"""
    f = dict(base)
    f.update({"start": start, "curPage": page, "pageSize": size, "totalCount": 0, "totalPage": 0})
    return f
