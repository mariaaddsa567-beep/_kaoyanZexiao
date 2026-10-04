# -*- coding: utf-8 -*-
"""分数线爬虫：研招网历年国家线（HTML 表格）+ 34 所自划线复试线公告（图片+链接）。"""
import json
import os
import re
import time

import requests

BASE = "https://yz.chsi.com.cn"
ZT_URL = BASE + "/kyzx/zt/kyfs.shtml"  # 复试分数线专题页
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE + "/",
}


def _get(url: str) -> str:
    r = requests.get(url, headers=H, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def _cells(tr: str) -> list[str]:
    out = []
    for c in re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", tr):
        txt = re.sub(r"<[^>]+>", "", c)
        txt = txt.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
        out.append(re.sub(r"\s+", "", txt))
    return out


def parse_national_table(html: str) -> list[dict]:
    """解析国家线表格：返回 [{category, code, sub, a_total, a1, a2, b_total, b1, b2}]。
    表头 2 行；门类行第一列含 [代码]，其后续无代码行为该门类子行（照顾专业/其他学科专业等）。"""
    tab = re.search(r"<table[\s\S]*?</table>", html)
    if not tab:
        return []
    rows = re.findall(r"<tr[\s\S]*?</tr>", tab.group(0))
    out, cur = [], None
    for tr in rows:
        c = _cells(tr)
        if len(c) < 3 or "学科门类" in c[0] and "A类" in "".join(c[:4]):
            continue
        m = re.match(r"^([\u4e00-\u9fa5]+)\[(\d{2})\][^\d]*$", c[0])
        if m:  # 门类行：c[1] 为子行说明（各学科专业/照顾专业等），数据从 c[2] 起
            cur = {"category": m.group(1), "code": m.group(2)}
            nums = [x for x in c[2:] if re.fullmatch(r"\d{1,3}", x)]
            if len(nums) >= 6:
                sub = c[1] if not re.fullmatch(r"\d{1,3}", c[1]) else "全部"
                out.append({**cur, "sub": sub, **_mk(nums)})
            continue
        if cur:  # 纯子行：无门类代码，归入当前门类（如工学-其他学科专业）
            nums = [x for x in c[1:] if re.fullmatch(r"\d{1,3}", x)]
            if len(nums) >= 6:
                out.append({**cur, "sub": c[0], **_mk(nums)})
    return out


def _mk(nums: list[str]) -> dict:
    return {
        "a_total": int(nums[0]), "a1": int(nums[1]), "a2": int(nums[2]),
        "b_total": int(nums[3]), "b1": int(nums[4]), "b2": int(nums[5]),
    }


def fetch_national_lines() -> list[dict]:
    """专题页 yearList -> 每年公告文章 -> 正文内链到 kp 路径表格文章 -> 解析表格。"""
    t = _get(ZT_URL)
    i = t.find("var yearList")
    j = t.find("];", i)
    seg = t[i:j]
    years = re.findall(r"year:\s*'(\d{4})',\s*url:\s*'([^']+)'", seg)
    out = []
    for year, url in years:
        html = _get(url if url.startswith("http") else BASE + url)
        rows = parse_national_table(html)
        if not rows:
            # yearList 文章是纯公告，真正的分数表在其正文链接（/kyzx/kp/）里
            links = re.findall(
                r'href="([^"]+/kyzx/kp/[^"]+\.html)"[^>]*>[^<]*初试成绩基本要求', html)
            if links:
                html = _get(links[0] if links[0].startswith("http") else BASE + links[0])
                rows = parse_national_table(html)
        print(f"国家线 {year}: {len(rows)} 行")
        for r in rows:
            out.append({"year": year, **r})
        time.sleep(2.5)
    return out


def fetch_zhx_lines() -> list[dict]:
    """专题页 zhxList -> 34 所自划线每校每年公告文章 -> 正文图片与链接。"""
    t = _get(ZT_URL)
    i = t.find("var zhxList")
    j = t.find("];", i)
    seg = t[i:j]
    out = []
    for blk in re.split(r"yxmc:", seg)[1:]:
        m = re.match(r"\s*'([^']+)'", blk)
        if not m:
            continue
        name = m.group(1)
        for year, url in re.findall(r"year:\s*'(\d{4})',\s*url:\s*'([^']+)'", blk):
            try:
                html = _get(url if url.startswith("http") else BASE + url)
            except Exception as e:  # noqa: BLE001
                print(f"!! {name} {year}: {e}")
                continue
            k = html.find('id="article_dnull"')
            body = html[k:] if k >= 0 else html
            body = body.split("近期热点")[0]
            imgs = re.findall(r'src="(https?://t\d+\.chei\.com\.cn/news/img/[^"]+)"', body)
            pdf = re.findall(r'href="([^"]+\.pdf)"', body)
            out.append({
                "school": name, "year": year,
                "article_url": url if url.startswith("http") else BASE + url,
                "imgs": list(dict.fromkeys(imgs)),
                "pdf": pdf[0] if pdf else "",
            })
            print(f"自划线 {name} {year}: 图 {len(imgs)} pdf={'Y' if pdf else '-'}")
            time.sleep(2.5)
    return out


def main():
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, "fsx.json")
    d = {"national": [], "zhx": []}
    if os.path.exists(path):
        d = json.load(open(path, encoding="utf-8"))
    if not d.get("national"):
        d["national"] = fetch_national_lines()
    if not d.get("zhx"):
        d["zhx"] = fetch_zhx_lines()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    print(f"国家线 {len(d['national'])} 行；自划线公告 {len(d['zhx'])} 条")


if __name__ == "__main__":
    main()
