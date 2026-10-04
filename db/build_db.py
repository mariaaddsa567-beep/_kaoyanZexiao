# -*- coding: utf-8 -*-
"""中间 JSON -> SQLite（data/kaoyan.db）。"""
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

SCHEMA = """
DROP TABLE IF EXISTS admissions;
DROP TABLE IF EXISTS school_major;
DROP TABLE IF EXISTS majors;
DROP TABLE IF EXISTS schools;
DROP TABLE IF EXISTS national_lines;
DROP TABLE IF EXISTS zhx_lines;

CREATE TABLE schools (
    dwdm TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    province TEXT,
    category TEXT,
    is_985 INTEGER DEFAULT 0,
    is_211 INTEGER DEFAULT 0,
    is_dual INTEGER DEFAULT 0,
    is_zhx INTEGER DEFAULT 0,
    sr_rank INTEGER,
    sr_cs_rank INTEGER,
    sr_cs_score REAL,
    sr_se_rank INTEGER,
    sr_se_score REAL,
    sr_cyb_rank INTEGER,
    sr_cyb_score REAL
);

CREATE TABLE majors (
    zydm TEXT PRIMARY KEY,
    zymc TEXT NOT NULL,
    group_key TEXT NOT NULL,   -- cs / se / cyb / xx
    yjxkdm TEXT,
    yjxkmc TEXT,
    xwlx TEXT,
    xwlxmc TEXT
);

CREATE TABLE school_major (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dwdm TEXT NOT NULL,
    zydm TEXT NOT NULL,
    yxs_list TEXT,          -- 院系所（去重，逗号分隔）
    yjfx_count INTEGER,     -- 研究方向数
    nzsrs_sum INTEGER,      -- 拟招生合计（含推免口径）
    nzsrs_str TEXT,         -- 招生人数描述（取首个非空）
    kskm_set TEXT,          -- 考试科目组合（去重，||分隔）
    has_408 INTEGER DEFAULT 0,
    xxfs_set TEXT,          -- 学习方式
    zybz TEXT               -- 专业备注（首个非空）
);

CREATE TABLE admissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dwdm TEXT NOT NULL,
    zydm TEXT NOT NULL,
    zymc TEXT,
    yxsdm TEXT,
    yxsmc TEXT,
    yjfxdm TEXT,
    yjfxmc TEXT,
    nzsrs INTEGER,
    nzsrsstr TEXT,
    ksfsmc TEXT,
    xxfs TEXT,
    km1 TEXT, km2 TEXT, km3 TEXT, km4 TEXT,
    zybz TEXT
);

CREATE INDEX idx_sm_dwdm ON school_major(dwdm);
CREATE INDEX idx_sm_zydm ON school_major(zydm);
CREATE INDEX idx_ad_dwdm ON admissions(dwdm);
CREATE INDEX idx_ad_zydm ON admissions(zydm);

CREATE TABLE national_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year TEXT NOT NULL,
    category TEXT NOT NULL,   -- 门类名（工学）
    code TEXT NOT NULL,       -- 门类代码（08）
    sub TEXT,                 -- 子行（其他学科专业/照顾专业等）
    a_total INTEGER, a1 INTEGER, a2 INTEGER,
    b_total INTEGER, b1 INTEGER, b2 INTEGER
);

CREATE TABLE zhx_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    school_name TEXT NOT NULL,  -- 校名（norm 后与 schools.name 匹配）
    year TEXT NOT NULL,
    article_url TEXT,
    imgs TEXT,                  -- 公告分数表图片 URL（|分隔）
    pdf TEXT
);
"""

GROUP_BY_YJXK = {"0812": "cs", "0835": "se", "0839": "cyb", "0854": "xx"}


def norm(name: str) -> str:
    return (name or "").replace("（", "(").replace("）", ")").replace(" ", "").strip()


def build():
    schools = json.load(open(os.path.join(DATA, "schools.json"), encoding="utf-8"))
    raw = json.load(open(os.path.join(DATA, "admissions_raw.json"), encoding="utf-8"))

    db = os.path.join(DATA, "kaoyan.db")
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)

    # ---- schools（软科名单 + 研招网出现的招生单位合并）----
    name2dwdm = {}
    sch_rows = {}
    for r in raw:
        name2dwdm[norm(r["school"]["dwmc"])] = r["school"]["dwdm"]

    for u in schools:
        key = norm(u["name"])
        dwdm = name2dwdm.get(key)
        if not dwdm:
            continue  # 未招生的学校（如部分文科类 211）不进库，详情里若出现则后补
        sch_rows[dwdm] = {
            "dwdm": dwdm, "name": u["name"],
            "province": u.get("province") or "",
            "category": u.get("category") or "",
            "is_985": u.get("rank_985") or 0,
            "is_211": u.get("rank_211") or 0,
            "is_dual": u.get("dual_class") or 0,
            "sr_rank": u.get("sr_rank"),
            "sr_cs_rank": u.get("sr_cs_rank"), "sr_cs_score": u.get("sr_cs_score"),
            "sr_se_rank": u.get("sr_se_rank"), "sr_se_score": u.get("sr_se_score"),
            "sr_cyb_rank": u.get("sr_cyb_rank"), "sr_cyb_score": u.get("sr_cyb_score"),
        }

    # ---- majors / school_major / admissions ----
    majors = {}
    sm = {}      # (dwdm, zydm) -> aggregate
    ad_rows = []

    def km_texts(item, idx):
        try:
            vo = item["kskmz"][0].get(f"km{idx}Vo") or {}
            return vo.get("kskmmc") or ""
        except (KeyError, IndexError, TypeError):
            return ""

    for r in raw:
        mj = r["major"]
        sch = r["school"]
        dwdm = sch["dwdm"]
        zydm = mj["zydm"]
        gkey = GROUP_BY_YJXK.get(mj["yjxkdm"], "xx")
        majors[zydm] = {
            "zydm": zydm, "zymc": mj["zymc"], "group_key": gkey,
            "yjxkdm": mj["yjxkdm"], "yjxkmc": mj["yjxkmc"],
            "xwlx": mj["xwlx"],
            "xwlxmc": "学术学位" if mj["xwlx"] == "xs" else "专业学位",
        }

        yxs, yjfx, nzsrs_sum, nzsrs_str, kmset, xxfsset, bz = set(), set(), 0, "", set(), set(), ""
        has408 = 0
        for it in r["details"]:
            yxs.add(it.get("yxsmc") or "")
            yjfx.add((it.get("yjfxmc") or ""))
            nzsrs_sum += int(it.get("nzsrs") or 0)
            nzsrs_str = nzsrs_str or it.get("nzsrsstr") or ""
            km = " | ".join(filter(None, [km_texts(it, i) for i in (1, 2, 3, 4)]))
            if km:
                kmset.add(km)
            if "408" in km or "计算机学科专业基础" in km:
                has408 = 1
            xxfsset.add(it.get("xxfs") or "")
            bz = bz or (it.get("zybz") or "")
            ad_rows.append((
                dwdm, zydm, mj["zymc"], it.get("yxsdm"), it.get("yxsmc"),
                it.get("yjfxdm"), it.get("yjfxmc"), it.get("nzsrs"), it.get("nzsrsstr"),
                it.get("ksfsmc"), it.get("xxfs"),
                km_texts(it, 1), km_texts(it, 2), km_texts(it, 3), km_texts(it, 4),
                it.get("zybz"),
            ))

        if r["details"]:
            sm[(dwdm, zydm)] = (
                "、".join(sorted(x for x in yxs if x)), len(yjfx), nzsrs_sum, nzsrs_str,
                " || ".join(sorted(kmset)), has408,
                "、".join(sorted(x for x in xxfsset if x)), bz,
            )
        else:
            sm[(dwdm, zydm)] = ("", 0, None, "", "", 0, "", "")

    # 补充：raw 中出现但软科缺失的学校
    for r in raw:
        sch = r["school"]
        if sch["dwdm"] not in sch_rows:
            sch_rows[sch["dwdm"]] = {
                "dwdm": sch["dwdm"], "name": sch["dwmc"],
                "province": sch.get("province") or "", "category": "",
                "is_985": 0, "is_211": 0, "is_dual": 0, "sr_rank": None,
                "sr_cs_rank": None, "sr_cs_score": None,
                "sr_se_rank": None, "sr_se_score": None,
                "sr_cyb_rank": None, "sr_cyb_score": None,
            }

    # is_zhx 来自 admissions_raw
    zhx_map = {r["school"]["dwdm"]: r["school"].get("zhx") == "1" for r in raw}
    for row in sch_rows.values():
        row["is_zhx"] = 1 if zhx_map.get(row["dwdm"]) else 0
    con.executemany(
        """INSERT INTO schools (dwdm,name,province,category,is_985,is_211,is_dual,is_zhx,sr_rank,
           sr_cs_rank,sr_cs_score,sr_se_rank,sr_se_score,sr_cyb_rank,sr_cyb_score)
           VALUES (:dwdm,:name,:province,:category,:is_985,:is_211,:is_dual,:is_zhx,:sr_rank,
           :sr_cs_rank,:sr_cs_score,:sr_se_rank,:sr_se_score,:sr_cyb_rank,:sr_cyb_score)""",
        list(sch_rows.values()),
    )
    con.executemany(
        "INSERT INTO majors VALUES (:zydm,:zymc,:group_key,:yjxkdm,:yjxkmc,:xwlx,:xwlxmc)",
        list(majors.values()),
    )
    con.executemany(
        """INSERT INTO school_major (dwdm,zydm,yxs_list,yjfx_count,nzsrs_sum,nzsrs_str,kskm_set,has_408,xxfs_set,zybz)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [(k[0], k[1], *v) for k, v in sm.items()],
    )
    con.executemany(
        """INSERT INTO admissions (dwdm,zydm,zymc,yxsdm,yxsmc,yjfxdm,yjfxmc,nzsrs,nzsrsstr,ksfsmc,xxfs,km1,km2,km3,km4,zybz)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ad_rows,
    )

    # ---- 分数线（fsx.json 存在时）----
    fsx_path = os.path.join(DATA, "fsx.json")
    if os.path.exists(fsx_path):
        fsx = json.load(open(fsx_path, encoding="utf-8"))
        con.executemany(
            """INSERT INTO national_lines (year,category,code,sub,a_total,a1,a2,b_total,b1,b2)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [(r["year"], r["category"], r["code"], r.get("sub") or "",
              r.get("a_total"), r.get("a1"), r.get("a2"),
              r.get("b_total"), r.get("b1"), r.get("b2")) for r in fsx.get("national", [])],
        )
        con.executemany(
            "INSERT INTO zhx_lines (school_name,year,article_url,imgs,pdf) VALUES (?,?,?,?,?)",
            [(norm(r["school"]), r["year"], r.get("article_url") or "",
              "|".join(r.get("imgs_local") or r.get("imgs") or []), r.get("pdf") or "")
             for r in fsx.get("zhx", [])],
        )
    con.commit()

    stat = {
        "schools": con.execute("SELECT COUNT(*) FROM schools").fetchone()[0],
        "majors": con.execute("SELECT COUNT(*) FROM majors").fetchone()[0],
        "school_major": con.execute("SELECT COUNT(*) FROM school_major").fetchone()[0],
        "admissions": con.execute("SELECT COUNT(*) FROM admissions").fetchone()[0],
    }
    print("DB built:", db, stat)


if __name__ == "__main__":
    build()
