# -*- coding: utf-8 -*-
"""对 OCR 失败/缺失数字的学校分数线图片进行增强重识别。

增强策略：放大 2-3 倍 + 灰度 + 自适应二值化 + 对比度提升，
然后用 RapidOCR 识别，结果合并到 zhx_scores_raw.json。
"""
import json
import os
import re

from PIL import Image, ImageEnhance, ImageFilter
from rapidocr_onnxruntime import RapidOCR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "zhx_scores_raw.json")
FSX = os.path.join(ROOT, "data", "fsx.json")

KEY_PAT = re.compile(r"工学|0812|0835|0839|0854|电子信息|计算机|软件工程|网络空间|人工智能|网络安全")
NUM_PAT = re.compile(r"^\d{2,4}$")

MISSING = [
    ("上海交通大学", "2024"), ("上海交通大学", "2026"),
    ("北京航空航天大学", "2023"), ("北京航空航天大学", "2024"),
    ("华南理工大学", "2024"),
    ("厦门大学", "2026"),
    ("吉林大学", "2023"),
    ("四川大学", "2024"),
    ("大连理工大学", "2024"),
    ("兰州大学", "2026"),
    ("西北工业大学", "2023"),
    ("西安交通大学", "2023"), ("西安交通大学", "2024"), ("西安交通大学", "2025"),
    ("重庆大学", "2025"), ("重庆大学", "2026"),
    ("东北大学", "2026"),
]


def enhance(img_path):
    """图像增强：放大、灰度、对比度、二值化。返回 PIL Image。"""
    img = Image.open(img_path)
    # 放大
    w, h = img.size
    scale = max(1, 1200 // max(w, h))
    if scale > 1:
        img = img.resize((w * scale, h * scale), Image.LANCZOS)
    # 灰度
    img = img.convert("L")
    # 对比度
    img = ImageEnhance.Contrast(img).enhance(2.0)
    # 锐化
    img = img.filter(ImageFilter.SHARPEN)
    return img


def cluster_rows(items, tol=12.0):
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
    fsx = json.load(open(FSX, encoding="utf-8"))
    raw = json.load(open(RAW, encoding="utf-8"))

    # 构建 school+year -> imgs_local 映射
    imgs_map = {}
    for z in fsx["zhx"]:
        imgs_map.setdefault((z["school"], z["year"]), []).extend(z.get("imgs_local") or [])

    # 移除这些学校-年份的旧 OCR 结果，准备重跑
    missing_keys = set(MISSING)
    raw = [r for r in raw if (r["school"], r["year"]) not in missing_keys]

    new_count = 0
    for school, year in MISSING:
        imgs = imgs_map.get((school, year), [])
        for img in imgs:
            path = os.path.join(ROOT, "app", img.lstrip("/"))
            if not os.path.exists(path):
                print(f"  跳过（不存在）: {school} {year} {img}")
                continue
            try:
                enhanced = enhance(path)
                tmp = os.path.join(ROOT, "data", "_ocr_tmp.png")
                enhanced.save(tmp)
                res, _ = eng(tmp)
                items = res or []
                rows = cluster_rows([(b, t, c) for b, t, c in items])
                hits = [
                    {"y": round(r["y"]), "text": r["text"], "nums": r["nums"]}
                    for r in rows if r["kw"]
                ]
                if hits:
                    raw.append({"school": school, "year": year, "img": img, "hits": hits})
                    new_count += 1
                    print(f"  OK {school} {year} {img}: {len(hits)} 命中行")
                    for h in hits[:3]:
                        print(f"    {h['text'][:80]} | nums={h['nums']}")
                else:
                    print(f"  无命中 {school} {year} {img}")
            except Exception as e:
                print(f"  !! 失败 {school} {year} {img}: {e}")

    json.dump(raw, open(RAW, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n新增 {new_count} 条 OCR 记录，总计 {len(raw)} 条")


if __name__ == "__main__":
    main()
