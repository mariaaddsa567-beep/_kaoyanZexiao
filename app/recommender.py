# -*- coding: utf-8 -*-
"""冲稳保推荐引擎 —— cs408 学科包 v1（按执行文档第 6 节实现）。

数据现状与置信度策略（文档 6.3 / 5.1）：
- 自划线校（34 所）：score_records(scope='school')，来源=公告 OCR，confidence=B；
- 非自划线校：用国家线（scope='national'，工学-其他学科专业）作基准线，confidence=C；
- 数据年数 <2 或全为 C 级时输出"数据不足"，只给区间不给具体概率。
"""
import math

import db.funcs as dbf

SUBJECT_PACK = {
    "id": "cs408",
    "name": "计算机统考408",
    "full_score": 500,
    "rule_version": "v1",
}

# 分档阈值（文档 6.3）
TIER_CHONG, TIER_WEN = 0.35, 0.70
# 院校因素修正下限/上限（文档 6.3：歧视/复试占比/推免占比 → 0.85~0.95 乘数）
ADJUST_ZHX = 0.95        # 自划线：划线晚、波动大
ADJUST_TUIMIAN = 0.92    # 招生计划少（≤10，推免挤压风险高）
SIGMA_FLOOR = 8.0


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _weighted_line(years: list[tuple[str, int]]) -> float:
    """years: [(year, line)] 近→远。B = 0.5*y1 + 0.3*y2 + 0.2*y3（文档 6.2）。"""
    ws = [0.5, 0.3, 0.2]
    total, used = 0.0, 0.0
    for (y, v), w in zip(years, ws):
        if v:
            total += v * w
            used += w
    return total / used if used else None


def _sigma(years: list[tuple[str, int]]) -> float:
    vals = [v for _, v in years if v]
    if len(vals) < 2:
        return SIGMA_FLOOR
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    return max(SIGMA_FLOOR, math.sqrt(var))


def national_base() -> dict:
    """国家线工学 A 区：{year: (total, s1, s2)}，按年份降序。"""
    rows = dbf.q(
        """SELECT year, a_total, a1, a2 FROM national_lines
           WHERE code='08' AND sub LIKE '%其他学科专业%' ORDER BY year DESC""")
    return {r["year"]: (r["a_total"], r["a1"], r["a2"]) for r in rows}


def school_lines(dwdm: str) -> list[dict]:
    return dbf.q(
        """SELECT year, initial_line, single1, single2, confidence, source
           FROM score_records WHERE dwdm=? AND scope='school'
           ORDER BY year DESC""", (dwdm,))


def predict_for_school(dwdm: str, nat: dict) -> dict:
    """预测该校工学计算机相关复试线。返回 {base, sigma, trend, confidence, years, note}。"""
    lines = school_lines(dwdm)
    trend = [(r["year"], r["initial_line"]) for r in lines if r["initial_line"]]
    if trend:
        base = _weighted_line(trend)
        sigma = _sigma(trend)
        conf = min((r["confidence"] for r in lines), default="B")
        note = "自划线院校公告校线"
        return {"base": base, "sigma": sigma, "trend": trend,
                "confidence": conf, "years": len(trend), "note": note}
    # 降级：国家线基准（confidence=C）
    nat_trend = [(y, v[0]) for y, v in sorted(nat.items(), reverse=True)]
    if nat_trend:
        base = _weighted_line(nat_trend)
        sigma = _sigma(nat_trend)
        return {"base": base, "sigma": sigma, "trend": nat_trend,
                "confidence": "C", "years": len(nat_trend),
                "note": "无校级公开线，以国家线为基准（实际复试线通常高于此）"}
    return {"base": None, "sigma": SIGMA_FLOOR, "trend": [],
            "confidence": "C", "years": 0, "note": "暂无分数数据"}


def hard_filter(p: dict, sch: dict, prog: dict) -> str | None:
    """文档 6.1 硬过滤。返回 None=通过，否则返回淘汰原因。"""
    if prog["exam_type"] != "408":
        return "非408"
    if p.get("math_type") and prog["math_type"] and prog["math_type"] != p["math_type"]:
        return f"要求{prog['math_type']}"
    if p.get("english_type") and prog["english_type"] and prog["english_type"] != p["english_type"]:
        return f"要求{prog['english_type']}"
    provs = p.get("provinces") or []
    if provs and sch["province"] not in provs:
        return "地域不符"
    levels = p.get("level_pref") or []
    if levels:
        ok = False
        for lv in levels:
            if lv == "985" and sch["is_985"]:
                ok = True
            if lv == "211" and (sch["is_211"] or sch["is_985"]):
                ok = True
        if not ok:
            return "层次不符"
    deg = p.get("degree_pref") or []
    if deg and prog["degree_type"] not in deg:
        return f"只要{'/'.join(deg)}"
    return None


def adjust_factor(sch: dict, prog: dict) -> tuple[float, list[str]]:
    """院校因素修正（文档 6.3），返回 (乘数, 风险项列表)。"""
    f, risks = 1.0, []
    if sch["is_zhx"]:
        f *= ADJUST_ZHX
        risks.append("自划线校：划线时间晚、波动大")
    if (prog["plan_total"] or 0) <= 10:
        f *= ADJUST_TUIMIAN
        risks.append(f"拟招生仅 {prog['plan_total']} 人：推免挤压与波动风险高")
    return f, risks


def recommend(profile: dict, limit_per_tier: int = 8) -> dict:
    """主入口：画像 → 冲稳保清单（可解释输出）。"""
    total = profile.get("total") or 0
    if not total:
        parts = ["ds", "co", "os", "cn", "math", "english", "politics"]
        total = sum(profile.get(k) or 0 for k in parts)
    if not total:
        return {"error": "请先填写预估总分或各科分数"}

    nat = national_base()
    cand = dbf.q("""
        SELECT p.id, p.dwdm, p.college, p.major_code, p.major_name, p.degree_type,
               p.direction, p.study_mode, p.plan_total, p.kskm, p.math_type, p.english_type,
               p.exam_type,
               s.name, s.province, s.is_985, s.is_211, s.is_zhx, s.sr_rank,
               s.sr_cs_rank, s.sr_cs_score
        FROM programs p JOIN schools s ON s.dwdm = p.dwdm
        WHERE p.exam_type='408'""")

    seen_school = {}   # 同校多方向只保留名额最多的
    for prog in cand:
        sch = {"province": prog["province"], "is_985": prog["is_985"],
               "is_211": prog["is_211"], "is_zhx": prog["is_zhx"]}
        reason = hard_filter(profile, sch, prog)
        if reason:
            continue
        key = (prog["dwdm"], prog["major_code"])
        cur = seen_school.get(key)
        if cur is None or (prog["plan_total"] or 0) > (cur["plan_total"] or 0):
            prog["_sch"] = sch
            seen_school[key] = prog

    results = []
    for key, prog in seen_school.items():
        sch = prog["_sch"]
        pred = predict_for_school(prog["dwdm"], nat)
        if pred["base"] is None:
            continue
        fac, risks = adjust_factor(sch, prog)
        p_raw = _sigmoid((total - pred["base"]) / (pred["sigma"] / 1.5))
        p_val = p_raw * fac
        insufficient = pred["confidence"] == "C" or pred["years"] < 2
        results.append({
            "school": prog["name"], "dwdm": prog["dwdm"],
            "province": prog["province"],
            "college": prog["college"], "major_code": prog["major_code"],
            "major_name": prog["major_name"], "degree_type": prog["degree_type"],
            "direction": prog["direction"], "study_mode": prog["study_mode"],
            "plan_total": prog["plan_total"], "kskm": prog["kskm"],
            "sr_cs_rank": prog["sr_cs_rank"],
            "predict_line": round(pred["base"]) if not insufficient else None,
            "line_range": [round(pred["base"] - pred["sigma"]),
                           round(pred["base"] + pred["sigma"])],
            "sigma": round(pred["sigma"]),
            "trend": pred["trend"],
            "diff": round(total - pred["base"]),
            "prob": None if insufficient else round(p_val * 100),
            "tier": ("冲" if p_val < TIER_CHONG else "稳" if p_val < TIER_WEN else "保"),
            "confidence": pred["confidence"],
            "data_years": pred["years"],
            "note": pred["note"],
            "risks": risks,
            "insufficient": insufficient,
        })

    # 排序：按概率降序，同档内按概率
    results.sort(key=lambda r: (r["prob"] if r["prob"] is not None else -1), reverse=True)
    tiers = {"冲": [], "稳": [], "保": [], "?": []}
    for r in results:
        tiers["?" if r["insufficient"] else r["tier"]].append(r)
    for t in tiers:
        tiers[t] = tiers[t][:limit_per_tier]
    combo = {"冲": 2, "稳": 3, "保": 2}
    plan = {t: tiers[t][:n] for t, n in combo.items()}

    return {
        "pack": SUBJECT_PACK,
        "user_total": total,
        "count": len(results),
        "tiers": tiers,
        "plan": plan,
        "disclaimer": "推荐结果基于公开数据估算，仅供参考，以院校官方公告为准；不构成任何录取承诺。",
    }
