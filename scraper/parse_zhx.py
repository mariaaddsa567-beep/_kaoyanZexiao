# -*- coding: utf-8 -*-
"""zhx_scores_raw.json（OCR 原始命中行）→ zhx_scores_parsed.json（每校每年多条校线）。

对每校每年，分别提取以下类别的分数线（各取一条最优）：
  - 工学门类线（08，不含照顾专业）
  - 计算机科学与技术（0812）
  - 软件工程（0835）
  - 网络空间安全（0839）
  - 电子信息专硕（0854）
总分 = nums 中 280~500 范围的最大值；单科 = 其余两位数。
confidence 全部标 B（文档 5.3：OCR 结果必须人工校对，前端展示原文图片供核对）。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "zhx_scores_raw.json")
OUT = os.path.join(ROOT, "data", "zhx_scores_parsed.json")

# 类别定义：(major_code, subject_name, [匹配关键词])
CATEGORIES = [
    ("0812", "计算机科学与技术", ["0812", "计算机科学", "计算机技术"]),
    ("0835", "软件工程", ["0835", "软件工程"]),
    ("0839", "网络空间安全", ["0839", "网络空间", "网络安全"]),
    ("0854", "电子信息", ["0854", "电子信息", "人工智能", "大数据"]),
    ("08", "工学", ["工学"]),  # 最后处理，兜底
]

# 工学照顾专业关键词，用于排除照顾专业线
CARE_PATS = ["照顾", "力学", "动力工程", "水利", "航空宇航", "兵器", "农业工程", "林业工程"]


def is_care_line(text):
    """判断是否为照顾专业行。注意：'不含力学/不含照顾' 表示非照顾线。"""
    # 先去除 "不含X" 的部分
    cleaned = text
    for pat in CARE_PATS:
        cleaned = cleaned.replace("不含" + pat, "")
    return any(p in cleaned for p in CARE_PATS)


def parse_line(row):
    """从一行 OCR 结果解析 (total, single1, single2)。"""
    nums = [int(n) for n in row["nums"]]
    totals = [n for n in nums if 280 <= n <= 500]
    if not totals:
        return None
    total = max(totals)
    singles = sorted(n for n in nums if n < 280)
    s1 = singles[0] if singles else None
    s2 = singles[1] if len(singles) > 1 else None
    return total, s1, s2


def pick_best(rows, keywords, exclude_care=False):
    """从命中行中选含关键词的最优行（总分最高）。exclude_care=True 时排除照顾专业行。
    若关键词行没有数字，尝试从相邻行（y 坐标接近）补全数字。"""
    # 按 y 排序
    sorted_rows = sorted(rows, key=lambda r: r.get("y", 0))
    best = None
    for idx, row in enumerate(sorted_rows):
        text = row["text"]
        if exclude_care and is_care_line(text):
            continue
        if not any(kw in text for kw in keywords):
            continue
        # 先尝试本行数字
        parsed = parse_line(row)
        if parsed:
            total, s1, s2 = parsed
            if best is None or total > best[0]:
                best = (total, s1, s2)
            continue
        # 本行无数字，尝试相邻行补全（前后各2行）
        nearby_nums = []
        for j in range(max(0, idx - 2), min(len(sorted_rows), idx + 3)):
            if j == idx:
                continue
            nearby_nums.extend(sorted_rows[j]["nums"])
        if nearby_nums:
            fake_row = {"nums": nearby_nums}
            parsed = parse_line(fake_row)
            if parsed:
                total, s1, s2 = parsed
                if best is None or total > best[0]:
                    best = (total, s1, s2)
    return best


def main():
    raw = json.load(open(RAW, encoding="utf-8"))
    name2dwdm = {}
    import sqlite3
    con = sqlite3.connect(os.path.join(ROOT, "data", "kaoyan.db"))
    for dwdm, name in con.execute("SELECT dwdm, name FROM schools"):
        name2dwdm[name.replace("（", "(").replace("）", ")").replace(" ", "")] = dwdm
    con.close()

    # 每校每年聚合所有图片的命中行
    grouped = {}
    for r in raw:
        grouped.setdefault((r["school"], r["year"]), []).extend(r["hits"])

    out = []
    for (school, year), hits in sorted(grouped.items()):
        dwdm = name2dwdm.get(school.replace("（", "(").replace("）", ")").replace(" ", ""), "")
        for major_code, subject, keywords in CATEGORIES:
            # 工学门类线需要排除照顾专业
            exclude = (major_code == "08")
            best = pick_best(hits, keywords, exclude_care=exclude)
            if best:
                total, s1, s2 = best
                out.append({
                    "dwdm": dwdm,
                    "school": school,
                    "year": year,
                    "major_code": major_code,
                    "subject": subject,
                    "initial_line": total,
                    "single1": s1,
                    "single2": s2,
                })
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"parsed {len(out)} 条 → {OUT}")
    # 按学校统计覆盖
    from collections import defaultdict
    cov = defaultdict(set)
    for r in out:
        cov[r["school"]].add(r["year"])
    for s in sorted(cov):
        print(f"  {s}: {sorted(cov[s])}")


if __name__ == "__main__":
    main()
