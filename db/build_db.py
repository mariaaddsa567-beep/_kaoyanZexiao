# -*- coding: utf-8 -*-
"""中间 JSON -> SQLite（data/kaoyan.db）。v2：按执行文档 5.2 数据模型重构。

新增：colleges（学院）、programs（报考点粒度：学院-专业-方向-学习方式，含
exam_type/math_type/english_type 硬筛选字段）、score_records（分数记录，含
来源与置信度）、retest_rules（复试规则，预留）。
"""
import json
import os
import re
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

SCHEMA = """
DROP TABLE IF EXISTS admissions;
DROP TABLE IF EXISTS school_major;
DROP TABLE IF EXISTS majors;
DROP TABLE IF EXISTS schools;
DROP TABLE IF EXISTS national_lines;
DROP TABLE IF EXISTS zhx_lines;
DROP TABLE IF EXISTS score_records;
DROP TABLE IF EXISTS retest_rules;
DROP TABLE IF EXISTS programs;
DROP TABLE IF EXISTS colleges;

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
    yxs_list TEXT,
    yjfx_count INTEGER,
    nzsrs_sum INTEGER,
    nzsrs_str TEXT,
    kskm_set TEXT,
    has_408 INTEGER DEFAULT 0,
    xxfs_set TEXT,
    zybz TEXT
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

-- 学院（院校-学院 两级，按文档 5.2）
CREATE TABLE colleges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dwdm TEXT NOT NULL,
    name TEXT NOT NULL,
    UNIQUE(dwdm, name)
);

-- 报考点粒度：学院-专业-方向-学习方式（文档 5.2 program）
CREATE TABLE programs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dwdm TEXT NOT NULL,
    college TEXT NOT NULL,
    year TEXT DEFAULT '2026',
    major_code TEXT NOT NULL,
    major_name TEXT,
    degree_type TEXT,          -- 学硕 / 专硕
    direction TEXT,            -- 研究方向
    study_mode TEXT,           -- 学习方式（全日制/非全日制）
    tuition REAL,
    duration TEXT,
    exam_type TEXT,            -- 408 / self_set / other
    math_type TEXT,            -- 数一 / 数二 / 非统考数学 / 空
    english_type TEXT,         -- 英一 / 英二 / 空
    plan_total INTEGER,        -- 拟招生（含推免口径）
    plan_tuimian INTEGER,
    plan_unified INTEGER,      -- 统考名额（暂等于 plan_total，推免数缺）
    official_url TEXT,
    kskm TEXT,                 -- 初试科目组合（展示用）
    zybz TEXT
);

-- 分数记录（校级线为主；scope: school=自划线校线, national=国家线基准）
CREATE TABLE score_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dwdm TEXT,
    school_name TEXT,
    year TEXT NOT NULL,
    scope TEXT NOT NULL,        -- school / national
    major_code TEXT,            -- 精确到专业时填（0812/0854...）
    subject TEXT,               -- 工学 / 电子信息 等
    initial_line INTEGER,       -- 复试线总分
    single1 INTEGER,            -- 单科(满分=100)
    single2 INTEGER,            -- 单科(满分>100)
    admit_min INTEGER, admit_avg INTEGER, admit_max INTEGER,
    apply_count INTEGER, interview_count INTEGER, admit_count INTEGER,
    source TEXT NOT NULL,       -- 来源
    confidence TEXT NOT NULL,   -- A/B/C（文档 5.1）
    updated_at TEXT
);

-- 复试规则（预留，v1 无数据）
CREATE TABLE retest_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dwdm TEXT,
    year TEXT,
    form TEXT,
    weight_initial REAL,
    weight_retest REAL,
    english_oral TEXT,
    discrimination_flag INTEGER DEFAULT 0,
    notes TEXT
);

CREATE INDEX idx_sm_dwdm ON school_major(dwdm);
CREATE INDEX idx_sm_zydm ON school_major(zydm);
CREATE INDEX idx_ad_dwdm ON admissions(dwdm);
CREATE INDEX idx_ad_zydm ON admissions(zydm);
CREATE INDEX idx_pg_dwdm ON programs(dwdm);
CREATE INDEX idx_pg_major ON programs(major_code);
CREATE INDEX idx_sr_dwdm ON score_records(dwdm);

CREATE TABLE national_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year TEXT NOT NULL,
    category TEXT NOT NULL,
    code TEXT NOT NULL,
    sub TEXT,
    a_total INTEGER, a1 INTEGER, a2 INTEGER,
    b_total INTEGER, b1 INTEGER, b2 INTEGER
);

CREATE TABLE zhx_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    school_name TEXT NOT NULL,
    year TEXT NOT NULL,
    article_url TEXT,
    imgs TEXT,
    pdf TEXT
);
"""

GROUP_BY_YJXK = {"0812": "cs", "0835": "se", "0839": "cyb", "0854": "xx"}


def norm(name: str) -> str:
    return (name or "").replace("（", "(").replace("）", ")").replace(" ", "").strip()


MATH_PAT = re.compile(r"数学[（(]([一二])[)）]|数学一|数学二")
ENG_PAT = re.compile(r"英语[（(]([一二])[)）]|英语一|英语二")


def classify_exam(kms: list[str]) -> tuple[str, str, str]:
    """从初试科目文本判断 exam_type / math_type / english_type。"""
    joined = " ".join(kms)
    if "408" in joined or "计算机学科专业基础" in joined:
        exam = "408"
    elif any(k for k in kms):
        exam = "self_set"
    else:
        exam = "other"
    m = MATH_PAT.search(joined)
    math_type = f"数{m.group(1)}" if m else ""
    e = ENG_PAT.search(joined)
    english_type = f"英{e.group(1)}" if e else ""
    return exam, math_type, english_type


def build():
    schools = json.load(open(os.path.join(DATA, "schools.json"), encoding="utf-8"))
    raw = json.load(open(os.path.join(DATA, "admissions_raw.json"), encoding="utf-8"))

    db = os.path.join(DATA, "kaoyan.db")
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)

    # ---- schools ----
    name2dwdm = {}
    for r in raw:
        name2dwdm[norm(r["school"]["dwmc"])] = r["school"]["dwdm"]
    sch_rows = {}
    for u in schools:
        dwdm = name2dwdm.get(norm(u["name"]))
        if not dwdm:
            continue
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

    # ---- majors / school_major / admissions（保留 v1 逻辑）----
    majors = {}
    sm = {}
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
        majors[zydm] = {
            "zydm": zydm, "zymc": mj["zymc"],
            "group_key": GROUP_BY_YJXK.get(mj["yjxkdm"], "xx"),
            "yjxkdm": mj["yjxkdm"], "yjxkmc": mj["yjxkmc"],
            "xwlx": mj["xwlx"],
            "xwlxmc": "学术学位" if mj["xwlx"] == "xs" else "专业学位",
        }
        yxs, yjfx, nzsrs_sum, nzsrs_str, kmset, xxfsset, bz = set(), set(), 0, "", set(), set(), ""
        has408 = 0
        for it in r["details"]:
            yxs.add(it.get("yxsmc") or "")
            yjfx.add(it.get("yjfxmc") or "")
            nzsrs_sum += int(it.get("nzsrs") or 0)
            nzsrs_str = nzsrs_str or it.get("nzsrsstr") or ""
            kms = [km_texts(it, i) for i in (1, 2, 3, 4)]
            km = " | ".join(filter(None, kms))
            if km:
                kmset.add(km)
            if "408" in km or "计算机学科专业基础" in km:
                has408 = 1
            xxfsset.add(it.get("xxfs") or "")
            bz = bz or (it.get("zybz") or "")
            ad_rows.append((
                dwdm, zydm, mj["zymc"], it.get("yxsdm"), it.get("yxsmc"),
                it.get("yjfxdm"), it.get("yjfxmc"), it.get("nzsrs"), it.get("nzsrsstr"),
                it.get("ksfsmc"), it.get("xxfs"), *kms, it.get("zybz"),
            ))
        sm[(dwdm, zydm)] = (
            "、".join(sorted(x for x in yxs if x)), len(yjfx),
            nzsrs_sum if r["details"] else None, nzsrs_str,
            " || ".join(sorted(kmset)), has408,
            "、".join(sorted(x for x in xxfsset if x)), bz,
        ) if r["details"] else ("", 0, None, "", "", 0, "", "")

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

    # ---- colleges + programs（v2：文档 5.2 粒度）----
    colleges = {}   # (dwdm, yxsmc) -> id
    pg_rows = []
    for r in ad_rows:
        (dwdm, zydm, zymc, _yxsdm, yxsmc, yjfxdm, yjfxmc, nzsrs, _nstr,
         ksfsmc, xxfs, km1, km2, km3, km4, zybz) = r
        key = (dwdm, yxsmc or "未分学院")
        if key not in colleges:
            colleges[key] = len(colleges) + 1
        kms = [km1, km2, km3, km4]
        exam, mt, et = classify_exam(kms)
        mj = majors.get(zydm) or {}
        pg_rows.append({
            "dwdm": dwdm, "college": yxsmc or "未分学院", "major_code": zydm,
            "major_name": zymc or mj.get("zymc") or "",
            "degree_type": mj.get("xwlxmc") or "",
            "direction": yjfxmc or "", "study_mode": xxfs or "",
            "exam_type": exam, "math_type": mt, "english_type": et,
            "plan_total": nzsrs, "plan_unified": nzsrs,
            "kskm": " | ".join(filter(None, kms)), "zybz": zybz or "",
            "ksfsmc": ksfsmc or "",
        })
    con.executemany(
        "INSERT INTO colleges (id,dwdm,name) VALUES (?,?,?)",
        [(v, k[0], k[1]) for k, v in colleges.items()],
    )
    con.executemany(
        """INSERT INTO programs (dwdm,college,year,major_code,major_name,degree_type,direction,
           study_mode,tuition,duration,exam_type,math_type,english_type,plan_total,plan_tuimian,
           plan_unified,official_url,kskm,zybz) VALUES
           (:dwdm,:college,'2026',:major_code,:major_name,:degree_type,:direction,:study_mode,
            NULL,NULL,:exam_type,:math_type,:english_type,:plan_total,NULL,:plan_unified,NULL,
            :kskm,:zybz)""",
        pg_rows,
    )

    # ---- 分数线：国家线 + 自划线公告 ----
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
        # 国家线也写入 score_records（scope=national, confidence=A），供推荐查询统一口径
        con.executemany(
            """INSERT INTO score_records (dwdm,school_name,year,scope,major_code,subject,
               initial_line,single1,single2,source,confidence,updated_at)
               VALUES (NULL,NULL,?,'national','08',?, ?,?,?, '教育部/研招网国家线','A', ?)""",
            [(r["year"], f"{r['category']}-{r.get('sub') or ''}", r["a_total"],
              r["a1"], r["a2"], "2026-10") for r in fsx.get("national", [])
             if r["code"] == "08" and "其他学科专业" in (r.get("sub") or "")],
        )

    # ---- 自划线 OCR 分数（confidence=B，人工校对前不改 A）----
    ocr_path = os.path.join(DATA, "zhx_scores_parsed.json")
    if os.path.exists(ocr_path):
        parsed = json.load(open(ocr_path, encoding="utf-8"))
        con.executemany(
            """INSERT INTO score_records (dwdm,school_name,year,scope,major_code,subject,
               initial_line,single1,single2,source,confidence,updated_at)
               VALUES (?,?,?,'school',?,?,?,?,?, '研招网自划线公告(OCR)', 'B', '2026-10')""",
            [(r["dwdm"], r["school"], r["year"], r["major_code"], r["subject"],
              r["initial_line"], r.get("single1"), r.get("single2")) for r in parsed],
        )

    con.commit()
    stat = {
        t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("schools", "colleges", "programs", "score_records",
                  "majors", "school_major", "admissions", "national_lines")
    }
    print("DB built:", db, stat)


if __name__ == "__main__":
    build()
