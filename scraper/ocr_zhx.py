# -*- coding: utf-8 -*-
"""RapidOCR 提取 34 所自划线公告中的计算机相关分数行。

流程：fsx.json 的 imgs_local → 每图识别 → 按 y 坐标聚类成行 →
保留含工学/电子信息/计算机等关键词的行（含同行全部数字）→
data/zhx_scores_raw.json 供人工校对 → 校对后由 build_db 导入 score_records。
"""
import json
import os
import re

from rapidocr_onnxruntime import RapidOCR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_ROOT = os.path.join(ROOT, "app", "static", "fsx")
OUT = os.path.join(ROOT, "data", "zhx_scores_raw.json")

# 计算机相关的门类/专业/学位类别关键词
KEY_PAT = re.compile(r"工学|0812|0835|0839|0854|电子信息|计算机|软件工程|网络空间|人工智能|网络安全")
NUM_PAT = re.compile(r"^\d{2,4}$")


def cluster_rows(items, tol=9.0):
    """按 box 中心 y 聚类同一表格行，行内按 x 排序。items: [(box, text, conf)]"""
    rows = []
    for box, text, conf in items:
        y = (box[0][1] + box[2][1]) / 2
        x = (box[0][0] + box[2][0]) / 2
        placed = False
        for r in rows:
            if abs(r["y"] - y) <= tol:
                r["cells"].append((x, text, conf))
                r["y"] = (r["y"] * (len(r["cells"]) - 1) + y) / len(r["cells"])
                placed = True
                break
        if not placed:
            rows.append({"y": y, "cells": [(x, text, conf)]})
    for r in rows:
        r["cells"].sort(key=lambda c: c[0])
        r["text"] = " ".join(c[1] for c in r["cells"])
        r["nums"] = [c[1] for c in r["cells"] if NUM_PAT.match(c[1])]
        r["kw"] = KEY_PAT.findall(r["text"])
    rows.sort(key=lambda r: r["y"])
    return rows


def main():
    eng = RapidOCR()
    fsx = json.load(open(os.path.join(ROOT, "data", "fsx.json"), encoding="utf-8"))
    raw = []
    if os.path.exists(OUT):
        raw = json.load(open(OUT, encoding="utf-8"))
        done = {(r["school"], r["year"], r["img"]) for r in raw}
        print(f"已有 {len(raw)} 条记录，续跑")
    else:
        done = set()

    total = sum(len(z.get("imgs_local") or []) for z in fsx["zhx"])
    n = 0
    for z in fsx["zhx"]:
        school, year = z["school"], z["year"]
        for img in z.get("imgs_local") or []:
            n += 1
            key = (school, year, img)
            if key in done:
                continue
            path = os.path.join(ROOT, "app", img.lstrip("/"))
            if not os.path.exists(path):
                continue
            try:
                res, _ = eng(path)
            except Exception as e:  # noqa: BLE001
                print(f"!! OCR失败 {school} {year} {img}: {e}")
                continue
            items = res or []
            rows = cluster_rows([(b, t, c) for b, t, c in items])
            hits = [
                {"y": round(r["y"]), "text": r["text"], "nums": r["nums"]}
                for r in rows if r["kw"]
            ]
            if hits:
                raw.append({"school": school, "year": year, "img": img, "hits": hits})
            if n % 20 == 0:
                print(f"进度 {n}/{total}，命中 {len(raw)} 条")
                json.dump(raw, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(raw, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"完成：{total} 图，{len(raw)} 条含计算机相关行的记录 → {OUT}")


if __name__ == "__main__":
    main()
