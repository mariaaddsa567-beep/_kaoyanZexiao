# -*- coding: utf-8 -*-
"""软科数据源：中国大学综合排名（bcur API）+ 最好学科排名（bcsr 页面 payload）。"""
import json
import re

from .http_client import Http

BCUR_URL = "https://www.shanghairanking.cn/api/pub/v1/bcur?bcur_type=11&year={year}"
BCSR_PAGE = "https://www.shanghairanking.cn/rankings/bcsr/{year}/{disc}"


def fetch_universities(year: int = 2024) -> list[dict]:
    """综合排名：校名、标签（985/211/双一流）、省份、类型、名次。"""
    http = Http("https://www.shanghairanking.cn/", min_interval=0.5)
    r = http.get(BCUR_URL.format(year=year))
    d = r.json()
    out = []
    for it in d["data"]["rankings"]:
        tags = it.get("univTags") or []
        out.append({
            "name": it["univNameCn"],
            "province": it.get("province") or "",
            "category": it.get("univCategory") or "",
            "rank_985": 1 if "985" in tags else 0,
            "rank_211": 1 if "211" in tags else 0,
            "dual_class": 1 if "双一流" in tags else 0,
            "sr_rank": int(re.sub(r"\D", "", str(it.get("ranking"))) or 0) or None,
        })
    return out


# ---------- bcsr payload（Nuxt JSONP 混淆）解析 ----------

def _split_top_args(s: str) -> list[str]:
    """按顶层逗号切分 JS 实参串（处理嵌套括号与字符串）。"""
    args, depth, cur, i = [], 0, [], 0
    in_str, esc = False, False
    while i < len(s):
        ch = s[i]
        if in_str:
            cur.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            cur.append(ch)
        elif ch in "([{":
            depth += 1
            cur.append(ch)
        elif ch in ")]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    if cur:
        args.append("".join(cur).strip())
    return args


def _parse_bcsr_payload(t: str) -> list[dict]:
    """从 __NUXT_JSONP__ 文本还原学校排名记录。"""
    try:
        p_sig = t.index("(function(") + len("(function(")
        p_body = t.index("){", p_sig) + 2  # 形参列表结束，函数体开始（含前置赋值语句）
        body_end = t.rindex("}(")  # 函数体闭合 + 实参列表开始
        params = [p.strip() for p in t[p_sig:p_body - 2].split(",")]
        body = t[p_body:body_end]
        arg_str = t[body_end + 2:]
        if arg_str.endswith("));"):
            arg_str = arg_str[:-3]
        elif arg_str.endswith(");"):
            arg_str = arg_str[:-2]
    except ValueError:
        return []
    vals = _split_top_args(arg_str)
    mapping = dict(zip(params, vals))

    # 整词替换形参标识符 -> 实参字面量（字符串内英文词误替换风险低，不影响字段提取）
    ident_re = re.compile(r"[A-Za-z_$][\w$]*")
    expanded = ident_re.sub(lambda m: mapping.get(m.group(0), m.group(0)), body)

    rows = []
    chunks = re.split(r"\{(?=univCode:)", expanded)
    for c in chunks[1:]:
        def field(key: str):
            mm = re.search(key + r":(\"(?:[^\"\\]|\\.)*\"|[^,}]+)", c)
            if not mm:
                return None
            v = mm.group(1)
            if v.startswith('"'):
                return json.loads(v)
            if v in ("null", "true", "false"):
                return {"null": None, "true": True, "false": False}[v]
            try:
                return int(v)
            except ValueError:
                return v
        rows.append({
            "univ": field("univNameCn"),
            "ranking": field("ranking"),
            "score": field("score"),
            "rank_pct": field("rankPctTopNum"),
        })
    return rows


def fetch_subject_ranking(year: int, disc: str) -> list[dict]:
    """最好学科排名：disc 为学科代码，如 0812。返回 [{univ, ranking, score}]。"""
    http = Http("https://www.shanghairanking.cn/", min_interval=0.8)
    r = http.get(BCSR_PAGE.format(year=year, disc=disc))
    m = re.search(r'href="(/_nuxt/static/[^"]+payload\.js)"', r.text)
    if not m:
        raise RuntimeError("bcsr 页面未找到 payload 路径")
    r2 = http.get("https://www.shanghairanking.cn" + m.group(1))
    return _parse_bcsr_payload(r2.text)


if __name__ == "__main__":
    us = fetch_universities()
    print("universities:", len(us), "985:", sum(u["rank_985"] for u in us), "211:", sum(u["rank_211"] for u in us))
    rows = fetch_subject_ranking(2024, "0812")
    print("0812 subject rows:", len(rows))
    print(rows[:3])
