# -*- coding: utf-8 -*-
"""zhx_scores_raw.json（OCR 原始命中行）→ zhx_scores_parsed.json（每校每年一条校线）。

行优先级：含 0812/计算机 > 0854/电子信息/人工智能/网络 > 工学（门类校线）。
总分 = nums 中 280~500 范围的最大值；单科 = 其余两位数。
confidence 全部标 B（文档 5.3：OCR 结果必须人工校对，前端展示原文图片供核对）。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "zhx_scores_raw.json")
OUT = os.path.join(ROOT, "data", "zhx_scores_parsed.json")

PRI = [
    ("0812", "工学-0812"), ("计算机", "工学-0812"),
    ("0854", "电子信息-0854"), ("电子信息", "电子信息-0854"),
    ("人工智能", "电子信息-0854"), ("网络", "电子信息-0854"), ("0854", "电子信息-0854"),
    ("0835", "工学-0835"), ("软件", "工学-0835"),
    ("0839", "工学-0839"), ("网络空间", "工学-0839"), ("网络安全", "工学-0839"),
    ("工学", "工学-08"),
]


def pick(rows):
    """从命中行选最优一条：PRI 序号小者优先，同级取总分更高者。"""
    best, best_pri = None, 99
    for row in rows:
        nums = [int(n) for n in row["nums"]]
        totals = [n for n in nums if 280 <= n <= 500]
        singles = sorted(n for n in nums if n < 280)
        if not totals:
            continue
        total = max(totals)
        for i, (pat, subj) in enumerate(PRI):
            if pat in row["text"]:
                if i < best_pri or (i == best_pri and best and total > best[0]):
                    best = (total, singles[0] if singles else None,
                            singles[1] if len(singles) > 1 else None, subj)
                    best_pri = i
                break
    return best


def main():
    raw = json.load(open(RAW, encoding="utf-8"))
    name2dwdm = {}
    import sqlite3
    con = sqlite3.connect(os.path.join(ROOT, "data", "kaoyan.db"))
    for dwdm, name in con.execute("SELECT dwdm, name FROM schools"):
        name2dwdm[name.replace("（", "(").replace("）", ")").replace(" ", "")] = dwdm
    con.close()

    # 每校每年聚合所有图片的命中行再挑最优
    grouped = {}
    for r in raw:
        grouped.setdefault((r["school"], r["year"]), []).extend(r["hits"])

    out = []
    for (school, year), hits in sorted(grouped.items()):
        best = pick(hits)
        if not best:
            continue
        line, s1, s2, subject = best
        out.append({
            "dwdm": name2dwdm.get(school.replace("（", "(").replace("）", ")").replace(" ", ""), ""),
            "school": school, "year": year, "major_code": subject.split("-")[1],
            "subject": subject.split("-")[0],
            "initial_line": line, "single1": s1, "single2": s2,
        })
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"parsed {len(out)} 条 → {OUT}")
    for r in out[:8]:
        print(" ", r["school"], r["year"], r["subject"], r["initial_line"])


if __name__ == "__main__":
    main()
