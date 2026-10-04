# -*- coding: utf-8 -*-
"""主爬取入口：软科（学校名单+学科排名）+ 研招网（专业目录），输出中间 JSON。"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper import chsi, shanghairanking  # noqa: E402
from scraper.official_lists import normalize, target_school_names  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
YEAR = 2024

SUBJECT_RANKS = [
    ("0812", "cs"),   # 计算机科学与技术
    ("0835", "se"),   # 软件工程
    ("0839", "cyb"),  # 网络空间安全
]


def log(msg: str):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def main():
    os.makedirs(DATA, exist_ok=True)
    schools_path = os.path.join(DATA, "schools.json")

    # 1) 软科：学校名单 + 学科排名（已落盘则跳过，便于断点续跑）
    if os.path.exists(schools_path):
        log("schools.json 已存在，跳过软科抓取")
        unis = json.load(open(schools_path, encoding="utf-8"))
    else:
        log("抓取软科综合排名 ...")
        unis = shanghairanking.fetch_universities(YEAR)
        official = target_school_names()
        # 官方名单兜底：软科未覆盖的 211/985 补进列表
        have = {normalize(u["name"]) for u in unis}
        for n in sorted(official - have):
            unis.append({
                "name": n, "province": "", "category": "",
                "rank_985": 0, "rank_211": 0, "dual_class": 0, "sr_rank": None,
            })
        for u in unis:
            n = normalize(u["name"])
            if n in official and not (u["rank_985"] or u["rank_211"]):
                # 软科没打标的官方 211/985 校补标（985 优先）
                u["rank_211"] = 1

    official = target_school_names()
    names_985_211 = {normalize(u["name"]) for u in unis if u["rank_985"] or u["rank_211"]}
    names_985_211 |= official
    # 研招网校名用全角括号（如「中国石油大学（北京）」），
    # 按校名精确查询需同时准备全角变体（仅含括号的名字有差异）
    names_985_211 |= {n.replace("(", "（").replace(")", "）")
                      for n in names_985_211 if "(" in n or ")" in n}
    log(f"学校 {len(unis)} 所，985/211 目标 {len(names_985_211)} 个名称")

    if not os.path.exists(schools_path):
        # 2) 软科最好学科排名（并发抓 3 个学科）
        def grab(disc_key):
            disc, key = disc_key
            try:
                rows = shanghairanking.fetch_subject_ranking(YEAR, disc)
                log(f"学科排名 {disc}: {len(rows)} 条")
                return key, rows
            except Exception as e:  # noqa: BLE001
                log(f"!! 学科排名 {disc} 失败: {e}")
                return key, []

        subj = {}
        name2uni = {normalize(u["name"]): u for u in unis}
        name2uni.update({u["name"]: u for u in unis})
        with ThreadPoolExecutor(3) as ex:
            for key, rows in ex.map(grab, SUBJECT_RANKS):
                subj[key] = rows
        for key, rows in subj.items():
            for r in rows:
                uni = name2uni.get(r["univ"]) or name2uni.get(normalize(r["univ"]))
                if uni:
                    uni[f"sr_{key}_rank"] = r["ranking"]
                    uni[f"sr_{key}_score"] = r["score"]

        with open(schools_path, "w", encoding="utf-8") as f:
            json.dump(unis, f, ensure_ascii=False, indent=1)

    # 3) 研招网专业目录（过滤到 985/211；增量 JSONL 支持断点续跑）
    log("开始研招网采集 ...")
    t0 = time.time()
    raw_path = os.path.join(DATA, "admissions_raw.jsonl")

    # 断点续跑：跳过已完成的 (dwdm, zydm)
    skip_pairs = set()
    if os.path.exists(raw_path):
        for line in open(raw_path, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                skip_pairs.add((r["school"]["dwdm"], r["major"]["zydm"]))
        log(f"已有 {len(skip_pairs)} 组记录，本次跳过")

    def cb(msg):
        log(msg)

    chsi.collect(names_985_211, progress_cb=cb, min_interval=2.5, workers=2,
                 sink_path=raw_path, skip_pairs=skip_pairs)

    records = [json.loads(line) for line in open(raw_path, encoding="utf-8") if line.strip()]
    with open(os.path.join(DATA, "admissions_raw.json"), "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    log(f"研招网完成：{len(records)} 组记录，耗时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
