# -*- coding: utf-8 -*-
"""考研择校 Web 服务：SQLite 查询 API + 静态页面。"""
import os
import sqlite3

from flask import Flask, jsonify, request, send_from_directory

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
        (SELECT COUNT(*) FROM school_major) AS points,
        (SELECT SUM(nzsrs_sum) FROM school_major) AS quota""")[0]
    return jsonify({"provinces": provinces, "majors": majors, "stats": stats})


@app.route("/api/schools")
def schools():
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
    rows = q(sql, args)
    return jsonify(rows)


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
    return jsonify({"school": sch[0], "majors": majors, "admissions": detail})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
