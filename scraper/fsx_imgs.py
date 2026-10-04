# -*- coding: utf-8 -*-
"""下载 34 所自划线公告图片到本地（外链图片在部分浏览器环境被拦截，本地化最稳）。"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
IMG_DIR = os.path.join(ROOT, "app", "static", "fsx")

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "", name).strip()


def dl(url: str, path: str) -> str:
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return "keep"
    r = requests.get(url, headers=H, timeout=30)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    return "dl"


def main():
    path = os.path.join(DATA, "fsx.json")
    d = json.load(open(path, encoding="utf-8"))
    tasks = []
    for z in d["zhx"]:
        folder = os.path.join(IMG_DIR, safe(z["school"]))
        os.makedirs(folder, exist_ok=True)
        local = []
        for n, u in enumerate(z.get("imgs") or []):
            ext = os.path.splitext(u.split("?")[0])[1] or ".jpg"
            fname = f"{z['year']}_{n}{ext}"
            tasks.append((u, os.path.join(folder, fname)))
            local.append(f"/static/fsx/{safe(z['school'])}/{fname}")
        z["imgs_local"] = local
    print(f"待下载 {len(tasks)} 张图片")
    ok = 0
    with ThreadPoolExecutor(4) as ex:
        for (u, p), res in zip(tasks, ex.map(lambda t: dl(*t), tasks)):
            ok += res in ("dl", "keep")
            if ok % 50 == 0:
                print(f"  {ok}/{len(tasks)}")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    print(f"完成 {ok}/{len(tasks)}，写入 imgs_local")


if __name__ == "__main__":
    main()
