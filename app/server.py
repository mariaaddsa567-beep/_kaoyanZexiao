# -*- coding: utf-8 -*-
"""考研择校 Web 服务：SQLite 查询 API + 静态页面（v2：408 专项重构）。"""
import os
import sqlite3
import sys

from flask import Flask, jsonify, request, send_from_directory

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recommender import SUBJECT_PACK, recommend  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "kaoyan.db")
STATIC = os.path.join(ROOT, "app", "static")

app = Flask(__name__)


def q(sql, args=()):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


@app.route("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC, filename)


@app.route("/api/meta")
def meta():
    provinces = [r["province"] for r in q(
        "SELECT DISTINCT province FROM schools WHERE province<>'' ORDER BY province")]
    majors = q("SELECT zydm, zymc, group_key, xwlxmc FROM majors ORDER BY group_key, zydm")
    stats = q("""SELECT
        (SELECT COUNT(*) FROM schools) AS schools,
        (SELECT COUNT(*) FROM programs WHERE exam_type='408') AS programs408,
        (SELECT COUNT(*) FROM programs) AS programs_all,
        (SELECT COUNT(*) FROM school_major) AS points""")[0]
    return jsonify({"provinces": provinces, "majors": majors, "stats": stats,
                    "pack": SUBJECT_PACK})


@app.route("/api/schools")
def schools():
    """校级列表（原有接口，保留）。"""
    kw = request.args.get("k", "").strip()
    province = request.args.get("province", "")
    tag = request.args.get("tag", "all")
    group = request.args.get("group", "")
    subject408 = request.args.get("subject408", "")
    xxfs = request.args.get("xxfs", "")
    sort = request.args.get("sort", "sr_rank")
    size = min(int(request.args.get("size", 200)), 500)

    where, args = ["1=1"], []
    if kw:
        where.append("(s.name LIKE ? OR CAST(s.dwdm AS TEXT) LIKE ?)")
        args += [f"%{kw}%", f"%{kw}%"]
    if province:
        where.append("s.province = ?")
        args.append(province)
    if tag == "985":
        where.append("s.is_985=1")
    elif tag == "211":
        where.append("s.is_211=1")
    elif tag == "zhx":
        where.append("s.is_zhx=1")
    if group:
        where.append("EXISTS (SELECT 1 FROM school_major sm JOIN majors m ON sm.zydm=m.zydm "
                     "WHERE sm.dwdm=s.dwdm AND m.group_key=?)")
        args.append(group)
    if subject408 == "1":
        where.append("EXISTS (SELECT 1 FROM school_major sm WHERE sm.dwdm=s.dwdm AND sm.has_408=1)")
    if xxfs == "1":
        where.append("EXISTS (SELECT 1 FROM school_major sm WHERE sm.dwdm=s.dwdm "
                     "AND sm.xxfs_set LIKE '%1%')")

    order = {
        "sr_rank": "s.sr_rank IS NULL, s.sr_rank",
        "sr_cs_rank": "s.sr_cs_rank IS NULL, s.sr_cs_rank",
        "quota": "quota IS NULL, quota DESC",
        "name": "s.province, s.name",
    }.get(sort, "s.sr_rank IS NULL, s.sr_rank")

    sql = f"""
    SELECT s.dwdm, s.name, s.province, s.category, s.is_985, s.is_211, s.is_dual, s.is_zhx,
           s.sr_rank, s.sr_cs_rank, s.sr_se_rank, s.sr_cyb_rank,
           SUM(sm.nzsrs_sum) AS quota,
           COUNT(sm.zydm) AS major_cnt,
           MAX(sm.has_408) AS has_408,
           GROUP_CONCAT(DISTINCT m.group_key) AS groups
    FROM schools s
    LEFT JOIN school_major sm ON sm.dwdm = s.dwdm
    LEFT JOIN majors m ON m.zydm = sm.zydm
    WHERE {' AND '.join(where)}
    GROUP BY s.dwdm
    ORDER BY {order}
    LIMIT ?
    """
    args.append(size)
    return jsonify(q(sql, args))


@app.route("/api/programs")
def programs():
    """报考点粒度检索（文档 P0-2）：仅 408 统考项 + 硬筛选。"""
    kw = request.args.get("k", "").strip()
    province = request.args.get("province", "")
    tag = request.args.get("tag", "")          # 985 / 211 / zhx
    degree = request.args.get("degree", "")    # 学硕 / 专硕
    math_t = request.args.get("math", "")      # 数一 / 数二
    english_t = request.args.get("english", "")  # 英一 / 英二
    exam = request.args.get("exam", "408")     # 默认只显示 408；all/self_set
    group = request.args.get("group", "")      # cs/se/cyb/xx
    sort = request.args.get("sort", "plan")
    size = min(int(request.args.get("size", 200)), 1000)

    where, args = ["1=1"], []
    if exam == "408":
        where.append("p.exam_type='408'")
    elif exam == "self_set":
        where.append("p.exam_type='self_set'")
    if kw:
        where.append("(s.name LIKE ? OR p.major_name LIKE ? OR p.college LIKE ? "
                     "OR p.major_code LIKE ?)")
        args += [f"%{kw}%"] * 4
    if province:
        where.append("s.province=?")
        args.append(province)
    if tag == "985":
        where.append("s.is_985=1")
    elif tag == "211":
        where.append("s.is_211=1")
    elif tag == "zhx":
        where.append("s.is_zhx=1")
    if degree:
        where.append("p.degree_type=?")
        args.append(degree)
    if math_t:
        where.append("p.math_type=?")
        args.append(math_t)
    if english_t:
        where.append("p.english_type=?")
        args.append(english_t)
    if group:
        where.append("m.group_key=?")
        args.append(group)

    order = {
        "plan": "p.plan_total IS NULL, p.plan_total DESC",
        "rank": "s.sr_cs_rank IS NULL, s.sr_cs_rank",
        "name": "s.province, s.name, p.major_code",
    }.get(sort, "p.plan_total IS NULL, p.plan_total DESC")

    sql = f"""
    SELECT p.id, p.dwdm, s.name AS school, s.province, s.is_985, s.is_211, s.is_zhx,
           s.sr_rank, s.sr_cs_rank, p.college, p.major_code, p.major_name,
           p.degree_type, p.direction, p.study_mode, p.math_type, p.english_type,
           p.exam_type, p.plan_total, p.kskm
    FROM programs p JOIN schools s ON s.dwdm = p.dwdm
    LEFT JOIN majors m ON m.zydm = p.major_code
    WHERE {' AND '.join(where)}
    ORDER BY s.province, {order}
    LIMIT ?"""
    args.append(size)
    return jsonify(q(sql, args))


@app.route("/api/programs/<int:pid>")
def program_detail(pid):
    rows = q("""SELECT p.*, s.name AS school, s.province, s.is_985, s.is_211, s.is_zhx,
                s.sr_rank, s.sr_cs_rank, s.sr_cs_score
                FROM programs p JOIN schools s ON s.dwdm=p.dwdm WHERE p.id=?""", (pid,))
    if not rows:
        return jsonify({"error": "not found"}), 404
    prog = rows[0]
    scores = q("""SELECT year, scope, subject, initial_line, single1, single2,
                  source, confidence FROM score_records
                  WHERE dwdm=? OR (scope='national')
                  ORDER BY scope DESC, year DESC""", (prog["dwdm"],))
    return jsonify({"program": prog, "scores": scores})


@app.route("/api/schools/<dwdm>")
def school_detail(dwdm):
    sch = q("SELECT * FROM schools WHERE dwdm=?", (dwdm,))
    if not sch:
        return jsonify({"error": "not found"}), 404
    majors = q("""
        SELECT sm.zydm, m.zymc, m.group_key, m.xwlxmc, sm.yxs_list, sm.yjfx_count,
               sm.nzsrs_sum, sm.nzsrs_str, sm.kskm_set, sm.has_408, sm.zybz
        FROM school_major sm JOIN majors m ON m.zydm = sm.zydm
        WHERE sm.dwdm = ?
        ORDER BY m.group_key, sm.zydm""", (dwdm,))
    detail = q("""
        SELECT zymc, yxsmc, yjfxmc, nzsrs, nzsrsstr, ksfsmc, km1, km2, km3, km4, zybz
        FROM admissions WHERE dwdm=? ORDER BY zymc, yxsmc, yjfxdm""", (dwdm,))
    programs = q("""SELECT id, college, major_code, major_name, degree_type, direction,
                    study_mode, exam_type, math_type, english_type, plan_total, kskm
                    FROM programs WHERE dwdm=? ORDER BY major_code, college""", (dwdm,))
    scores = q("""SELECT year, scope, subject, initial_line, single1, single2,
                  source, confidence FROM score_records
                  WHERE dwdm=? ORDER BY year DESC""", (dwdm,))
    zhx_lines = []
    if sch[0].get("is_zhx"):
        name = sch[0]["name"].replace("（", "(").replace("）", ")").replace(" ", "")
        zhx_lines = q("""
            SELECT year, article_url, imgs, pdf FROM zhx_lines
            WHERE school_name = ? ORDER BY year DESC""", (name,))
    return jsonify({"school": sch[0], "majors": majors, "admissions": detail,
                    "programs": programs, "scores": scores, "zhx_lines": zhx_lines})


@app.route("/api/lines")
def lines():
    """国家线：工学[08] 其他学科专业（计算机学硕 0812/0835/0839 与专硕 0854 均执行此线）。"""
    rows = q("""
        SELECT year, a_total, a1, a2, b_total, b1, b2 FROM national_lines
        WHERE code='08' AND sub LIKE '%其他学科专业%'
        ORDER BY year DESC""")
    return jsonify(rows)


@app.route("/api/recommend", methods=["POST"])
def recommend_api():
    """冲稳保推荐（文档 P0-4）。入参：考生画像 JSON。"""
    profile = request.get_json(silent=True) or {}
    return jsonify(recommend(profile))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
