# -*- coding: utf-8 -*-
"""批量爬取各高校计算机学院复试名单，提取初试分数并计算统计量。

支持 HTML 表格和 PDF 两种格式。输出到 data/admit_scores_new.json，
与现有 admit_scores.json 合并后由 build_db 导入。
"""
import json
import os
import re
import statistics
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "admit_scores_new.json")

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# 学校代码映射
SCHOOL_DWDM = {
    "清华大学": "10003", "北京大学": "10001", "中国人民大学": "10002",
    "北京航空航天大学": "10006", "北京理工大学": "10007", "北京师范大学": "10027",
    "中国农业大学": "10019", "南开大学": "10055", "天津大学": "10056",
    "大连理工大学": "10141", "东北大学": "10145", "吉林大学": "10183",
    "哈尔滨工业大学": "10213", "复旦大学": "10246", "同济大学": "10247",
    "上海交通大学": "10248", "华东师范大学": "10269", "南京大学": "10284",
    "东南大学": "10286", "浙江大学": "10335", "中国科学技术大学": "10358",
    "厦门大学": "10384", "山东大学": "10422", "中国海洋大学": "10423",
    "武汉大学": "10486", "华中科技大学": "10487", "湖南大学": "10532",
    "中南大学": "10533", "中山大学": "10558", "华南理工大学": "10561",
    "四川大学": "10610", "重庆大学": "10611", "电子科技大学": "10614",
    "西安交通大学": "10698", "西北工业大学": "10699", "兰州大学": "10730",
}

# 专业名称到代码的映射
MAJOR_MAP = {
    "计算机科学与技术": "081200",
    "软件工程": "083500",
    "网络空间安全": "083900",
    "电子信息": "085400",
    "计算机技术": "085404",
    "软件工程专硕": "085405",
    "人工智能": "085410",
    "大数据技术与工程": "085411",
    "智能数字表演": "0812J1",
}


def get(url, retries=3, **kw):
    for i in range(retries):
        try:
            r = requests.get(url, headers=H, timeout=30, verify=False, **kw)
            r.raise_for_status()
            return r
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2)
    return None


def parse_html_table(html_text):
    """从 HTML 文本中提取表格行，返回 list[list[str]]。"""
    # 去掉标签内的属性干扰，提取 <tr>...</tr>
    rows = []
    for tr in re.findall(r"<tr[\s\S]*?</tr>", html_text, re.I):
        cells = re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", tr, re.I)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        cells = [re.sub(r"\s+", " ", c).strip() for c in cells]
        if cells:
            rows.append(cells)
    return rows


def stats(scores):
    """计算 min/avg/max/count，过滤无效分数。"""
    scores = [s for s in scores if s and 200 <= s <= 500]
    if not scores:
        return None
    return {
        "admit_min": min(scores),
        "admit_avg": round(statistics.mean(scores), 1),
        "admit_max": max(scores),
        "interview_count": len(scores),
    }


def extract_score_from_cells(cells, total_idx=None):
    """从一行单元格中提取总分。优先找 280-500 范围的数值。"""
    nums = []
    for c in cells:
        # 提取数字
        for m in re.findall(r"\d+", c):
            n = int(m)
            if 200 <= n <= 500:
                nums.append(n)
    if not nums:
        return None
    # 如果指定了总分列索引，优先使用
    if total_idx is not None and total_idx < len(cells):
        m = re.search(r"\d+", cells[total_idx])
        if m:
            n = int(m.group())
            if 200 <= n <= 500:
                return n
    return max(nums)  # 取最大值作为总分


def scrape_nankai_2026():
    """南开大学计算机学院2026年复试结果（HTML表格）。"""
    url = "https://cyber.nankai.edu.cn/2026/0401/c13348a591970/page.htm"
    r = get(url)
    r.encoding = "utf-8"
    rows = parse_html_table(r.text)
    # 按专业分组收集总分
    by_major = {}
    for cells in rows:
        if len(cells) < 10:
            continue
        major = cells[0].strip()
        if major in ("复试专业", "计算机科学与技术", "电子信息"):
            if major == "复试专业":
                continue
            # 总分在第10列（索引9）
            score = extract_score_from_cells(cells, total_idx=9)
            if score:
                by_major.setdefault(major, []).append(score)
    out = []
    for major, scores in by_major.items():
        st = stats(scores)
        if st:
            out.append({
                "dwdm": SCHOOL_DWDM["南开大学"],
                "school_name": "南开大学",
                "year": "2026",
                "major_code": MAJOR_MAP.get(major, ""),
                "subject": major,
                **st,
                "source": "南开大学计算机学院2026年复试结果公示",
            })
    print(f"南开大学2026: {len(out)} 个专业")
    return out


def scrape_bit_2024():
    """北京理工大学计算机学院2024年复试拟录取名单（HTML表格）。"""
    url = "https://cs.bit.edu.cn/tzgg/8e68f3a2808a4758b8e593076b173dd2.htm"
    r = get(url)
    r.encoding = "utf-8"
    rows = parse_html_table(r.text)
    by_major = {}
    for cells in rows:
        if len(cells) < 7:
            continue
        # 第4列是报考专业名称（索引3），第5列是初试成绩（索引4）
        major = cells[3].strip()
        score_str = re.search(r"\d+", cells[4])
        if not score_str:
            continue
        score = int(score_str.group())
        if 200 <= score <= 500:
            by_major.setdefault(major, []).append(score)
    out = []
    for major, scores in by_major.items():
        st = stats(scores)
        if st:
            out.append({
                "dwdm": SCHOOL_DWDM["北京理工大学"],
                "school_name": "北京理工大学",
                "year": "2024",
                "major_code": MAJOR_MAP.get(major, ""),
                "subject": major,
                **st,
                "source": "北京理工大学计算机学院2024年复试拟录取名单",
            })
    print(f"北京理工大学2024: {len(out)} 个专业")
    return out


def scrape_sysu_2025():
    """中山大学计算机学院2025年复试结果（HTML表格）。"""
    url = "https://cse.sysu.edu.cn/article/3117"
    r = get(url)
    r.encoding = "utf-8"
    rows = parse_html_table(r.text)
    by_major = {}
    for cells in rows:
        if len(cells) < 11:
            continue
        # 第3列是初试总分（索引2），第6列是录取专业（索引5）
        score_str = re.search(r"\d+", cells[2])
        if not score_str:
            continue
        score = int(score_str.group())
        if not (200 <= score <= 500):
            continue
        major_raw = cells[5].strip()
        # 提取专业代码和名称，如 "081200 计算机科学与技术"
        m = re.match(r"(\d{6})\s*(.+)", major_raw)
        if m:
            code, name = m.group(1), m.group(2).strip()
        else:
            code, name = "", major_raw
        key = (code, name)
        by_major.setdefault(key, []).append(score)
    out = []
    for (code, name), scores in by_major.items():
        st = stats(scores)
        if st:
            out.append({
                "dwdm": SCHOOL_DWDM["中山大学"],
                "school_name": "中山大学",
                "year": "2025",
                "major_code": code,
                "subject": name,
                **st,
                "source": "中山大学计算机学院2025年复试结果公示",
            })
    print(f"中山大学2025: {len(out)} 个专业")
    return out


def scrape_scu_2025():
    """四川大学计算机学院2025年复试成绩（HTML表格）。"""
    url = "https://cs.scu.edu.cn/info/1266/19042.htm"
    r = get(url)
    r.encoding = "utf-8"
    rows = parse_html_table(r.text)
    by_major = {}
    for cells in rows:
        if len(cells) < 10:
            continue
        # 考生编号前6位是学校代码，7-12位是专业代码
        exam_id = cells[0].strip()
        score_str = re.search(r"\d+", cells[6])  # 初试总分在第7列（索引6）
        if not score_str:
            continue
        score = int(score_str.group())
        if not (200 <= score <= 500):
            continue
        # 从考生编号提取专业代码：106105 081200 0xxx
        m = re.match(r"106105(\d{6})", exam_id)
        if m:
            code = m.group(1)
        else:
            code = ""
        name = MAJOR_MAP_INV.get(code, code)
        by_major.setdefault((code, name), []).append(score)
    out = []
    for (code, name), scores in by_major.items():
        st = stats(scores)
        if st:
            out.append({
                "dwdm": SCHOOL_DWDM["四川大学"],
                "school_name": "四川大学",
                "year": "2025",
                "major_code": code,
                "subject": name,
                **st,
                "source": "四川大学计算机学院2025年复试成绩公示",
            })
    print(f"四川大学2025: {len(out)} 个专业")
    return out


# 专业代码到名称的映射
MAJOR_MAP_INV = {v: k for k, v in MAJOR_MAP.items()}
MAJOR_MAP_INV.update({
    "081200": "计算机科学与技术",
    "083500": "软件工程",
    "083900": "网络空间安全",
    "085400": "电子信息",
    "085404": "计算机技术",
    "085405": "软件工程",
    "085410": "人工智能",
    "085411": "大数据技术与工程",
})


def scrape_ustc_2025():
    """中国科学技术大学计算机学院2025年复试名单（HTML表格）。"""
    url = "https://cs.ustc.edu.cn/2025/0316/c22510a676968/pagem.htm"
    r = get(url)
    r.encoding = "utf-8"
    rows = parse_html_table(r.text)
    by_major = {}
    for cells in rows:
        if len(cells) < 9:
            continue
        # 第4列是报考专业（索引3），第9列是初试总分（索引8）
        major = cells[3].strip()
        score_str = re.search(r"\d+", cells[8])
        if not score_str:
            continue
        score = int(score_str.group())
        if 200 <= score <= 500:
            by_major.setdefault(major, []).append(score)
    out = []
    for major, scores in by_major.items():
        st = stats(scores)
        if st:
            out.append({
                "dwdm": SCHOOL_DWDM["中国科学技术大学"],
                "school_name": "中国科学技术大学",
                "year": "2025",
                "major_code": MAJOR_MAP.get(major, ""),
                "subject": major,
                **st,
                "source": "中国科学技术大学计算机学院2025年复试名单",
            })
    print(f"中国科学技术大学2025: {len(out)} 个专业")
    return out


def scrape_nju_ai_2026():
    """南京大学人工智能学院2026年复试名单（页面JS渲染，数据来自WebFetch）。"""
    # 计算机科学与技术：401, 399, 393, 392, 391, 383, 382, 371, 371, 363
    # 人工智能：390, 372, 368, 366, 359, 353
    data = {
        "计算机科学与技术": [401, 399, 393, 392, 391, 383, 382, 371, 371, 363],
        "人工智能": [390, 372, 368, 366, 359, 353],
    }
    out = []
    for major, scores in data.items():
        st = stats(scores)
        if st:
            out.append({
                "dwdm": SCHOOL_DWDM["南京大学"],
                "school_name": "南京大学",
                "year": "2026",
                "major_code": MAJOR_MAP.get(major, ""),
                "subject": major,
                **st,
                "source": "南京大学人工智能学院2026年复试名单",
            })
    print(f"南京大学(AI)2026: {len(out)} 个专业")
    return out


def scrape_jlu_2026():
    """吉林大学计算机学院2026年复试成绩PDF。"""
    import pdfplumber
    import io
    url = "https://ccst.jlu.edu.cn/system/_content/download.jsp?urltype=news.DownloadAttachUrl&owner=1840203934&wbfileid=18093076"
    headers = {**H, "Referer": "https://ccst.jlu.edu.cn/info/1094/20920.htm"}
    r = requests.get(url, headers=headers, timeout=30, verify=False)
    by_major = {}
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue
            for row in table:
                if not row:
                    continue
                cells = [str(c).strip().replace("\n", "") if c else "" for c in row]
                if not any(cells) or "考生编号" in cells[0]:
                    continue
                major_code = ""
                major_name = ""
                score = None
                for c in cells:
                    if re.match(r"^08\d{4}$", c):
                        major_code = c
                    elif c in ("计算机科学与技术", "软件工程", "网络空间安全",
                               "电子信息", "计算机技术", "人工智能"):
                        major_name = c
                    try:
                        n = int(c)
                        if 200 <= n <= 500 and score is None:
                            score = n
                    except (ValueError, TypeError):
                        pass
                if score and (major_code or major_name):
                    key = major_code or major_name
                    by_major.setdefault(key, []).append(score)
    out = []
    for key, scores in by_major.items():
        st = stats(scores)
        if st:
            code = key if re.match(r"^\d{6}$", key) else MAJOR_MAP.get(key, "")
            name = MAJOR_MAP_INV.get(key, key) if re.match(r"^\d{6}$", key) else key
            out.append({
                "dwdm": SCHOOL_DWDM["吉林大学"],
                "school_name": "吉林大学",
                "year": "2026",
                "major_code": code,
                "subject": name,
                **st,
                "source": "吉林大学计算机学院2026年复试成绩",
            })
    print(f"吉林大学2026: {len(out)} 个专业")
    return out


def scrape_dlut_2026():
    """大连理工大学计算机学院2026年复试成绩PDF。"""
    import pdfplumber
    import io
    url = "https://cs.dlut.edu.cn/system/_content/download.jsp?urltype=news.DownloadAttachUrl&owner=1970493474&wbfileid=63EFE49E2B1350B78A64AB3168A8E04A"
    headers = {**H, "Referer": "https://cs.dlut.edu.cn/info/1256/6060.htm"}
    r = requests.get(url, headers=headers, timeout=30, verify=False)
    by_major = {}
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue
            for row in table:
                if not row:
                    continue
                cells = [str(c).strip().replace("\n", "") if c else "" for c in row]
                if not any(cells) or "考生编号" in cells[0]:
                    continue
                major_code = ""
                major_name = ""
                score = None
                for c in cells:
                    if re.match(r"^08\d{4}$", c):
                        major_code = c
                    elif c in ("计算机科学与技术", "软件工程", "网络空间安全",
                               "电子信息", "计算机技术", "人工智能", "大数据技术与工程"):
                        major_name = c
                    try:
                        n = int(c)
                        if 200 <= n <= 500 and score is None:
                            score = n
                    except (ValueError, TypeError):
                        pass
                if score and (major_code or major_name):
                    key = major_code or major_name
                    by_major.setdefault(key, []).append(score)
    out = []
    for key, scores in by_major.items():
        st = stats(scores)
        if st:
            code = key if re.match(r"^\d{6}$", key) else MAJOR_MAP.get(key, "")
            name = MAJOR_MAP_INV.get(key, key) if re.match(r"^\d{6}$", key) else key
            out.append({
                "dwdm": SCHOOL_DWDM["大连理工大学"],
                "school_name": "大连理工大学",
                "year": "2026",
                "major_code": code,
                "subject": name,
                **st,
                "source": "大连理工大学计算机学院2026年复试成绩",
            })
    print(f"大连理工大学2026: {len(out)} 个专业")
    return out


def scrape_sdu_2026():
    """山东大学计算机学院2026年复试成绩PDF。"""
    import pdfplumber
    import io
    url = "https://www.cs.sdu.edu.cn/system/_content/download.jsp?urltype=news.DownloadAttachUrl&owner=1470795559&wbfileid=17924105"
    headers = {**H, "Referer": "https://www.cs.sdu.edu.cn/info/1068/6784.htm"}
    r = requests.get(url, headers=headers, timeout=30, verify=False)
    by_major = {}
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue
            for row in table:
                if not row or len(row) < 7:
                    continue
                cells = [str(c).strip().replace("\n", "") if c else "" for c in row]
                if "考生编号" in cells[0]:
                    continue
                major_code = cells[2]
                major_name = cells[3]
                try:
                    score = int(cells[4])
                    if 200 <= score <= 500:
                        by_major.setdefault((major_code, major_name), []).append(score)
                except (ValueError, IndexError):
                    continue
    out = []
    for (code, name), scores in by_major.items():
        st = stats(scores)
        if st:
            out.append({
                "dwdm": SCHOOL_DWDM["山东大学"],
                "school_name": "山东大学",
                "year": "2026",
                "major_code": code,
                "subject": name,
                **st,
                "source": "山东大学计算机学院2026年复试成绩",
            })
    print(f"山东大学2026: {len(out)} 个专业")
    return out


def scrape_xmu_2026():
    """厦门大学信息学院2026年复试名单PDF。"""
    import pdfplumber
    import io
    base = "https://informatics.xmu.edu.cn/system/_content/download.jsp?urltype=news.DownloadAttachUrl&owner=2125615903&wbfileid="
    files = {
        "计算机科学与技术": "ABA6E17940193ACCCF2F3B7AC926EE13",
        "人工智能": "52D26EBA5531C472B9BF418CE6C2D379",
        "软件工程": "224C316769441FE2B781BCA0E5476EF3",
    }
    headers = {**H, "Referer": "https://informatics.xmu.edu.cn/info/1072/200291.htm"}
    out = []
    for major, fid in files.items():
        url = base + fid
        try:
            r = requests.get(url, headers=headers, timeout=30, verify=False)
            scores = []
            with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                for page in pdf.pages:
                    table = page.extract_table()
                    if not table:
                        continue
                    for row in table:
                        if not row:
                            continue
                        for c in row:
                            if c is None:
                                continue
                            try:
                                n = int(str(c).strip())
                                if 280 <= n <= 500:
                                    scores.append(n)
                                    break
                            except (ValueError, TypeError):
                                continue
            st = stats(scores)
            if st:
                out.append({
                    "dwdm": SCHOOL_DWDM["厦门大学"],
                    "school_name": "厦门大学",
                    "year": "2026",
                    "major_code": MAJOR_MAP.get(major, ""),
                    "subject": major,
                    **st,
                    "source": "厦门大学信息学院2026年复试名单",
                })
        except Exception as e:
            print(f"  厦门大学 {major} 失败: {e}")
    print(f"厦门大学2026: {len(out)} 个专业")
    return out


def scrape_pdf_tongji_2025():
    """同济大学计算机学院2025年复试名单PDF。"""
    import pdfplumber
    url = "https://cs.tongji.edu.cn/__local/3/34/94/058EA73FFB58762767258144EE8_B976AF26_64C1D.pdf"
    r = get(url)
    scores = []
    with pdfplumber.open(__import__("io").BytesIO(r.content)) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue
            for row in table:
                if not row or len(row) < 7:
                    continue
                cells = [str(c).strip() if c else "" for c in row]
                if "考生编号" in cells[0] or "姓名" in cells[1]:
                    continue
                try:
                    score = int(cells[6])
                    if 200 <= score <= 500:
                        scores.append(score)
                except (ValueError, IndexError):
                    continue
    out = []
    st = stats(scores)
    if st:
        out.append({
            "dwdm": SCHOOL_DWDM["同济大学"],
            "school_name": "同济大学",
            "year": "2025",
            "major_code": "081200",
            "subject": "计算机科学与技术",
            **st,
            "source": "同济大学计算机学院2025年复试名单",
        })
    print(f"同济大学2025: {len(out)} 个专业 (n={len(scores)})")
    return out


def scrape_pdf(url, school_name, year, source, major_col=None, score_col=None,
               school_code_prefix=None):
    """通用 PDF 解析：下载 PDF，提取表格行。"""
    try:
        import pdfplumber
    except ImportError:
        print("pdfplumber 未安装，跳过 PDF 解析")
        return []
    r = get(url)
    tmp_path = os.path.join(ROOT, "data", "_tmp_admit.pdf")
    with open(tmp_path, "wb") as f:
        f.write(r.content)
    by_major = {}
    try:
        with pdfplumber.open(tmp_path) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if not table:
                    continue
                for row in table:
                    if not row:
                        continue
                    cells = [str(c).strip() if c else "" for c in row]
                    if not any(cells):
                        continue
                    # 跳过表头
                    if "考生编号" in cells or "姓名" in cells and "初试" in " ".join(cells):
                        continue
                    # 提取专业
                    major = ""
                    if major_col is not None and major_col < len(cells):
                        major = cells[major_col].strip()
                    # 提取总分
                    score = None
                    if score_col is not None and score_col < len(cells):
                        m = re.search(r"\d+", cells[score_col])
                        if m:
                            score = int(m.group())
                    if score is None:
                        score = extract_score_from_cells(cells)
                    if score and 200 <= score <= 500 and major:
                        by_major.setdefault(major, []).append(score)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    out = []
    for major, scores in by_major.items():
        st = stats(scores)
        if st:
            # 专业代码映射到名称
            code = MAJOR_MAP.get(major, "")
            name = major
            if re.match(r"^\d{6}$", major):
                code = major
                name = MAJOR_MAP_INV.get(major, major)
            out.append({
                "dwdm": SCHOOL_DWDM.get(school_name, ""),
                "school_name": school_name,
                "year": year,
                "major_code": code,
                "subject": name,
                **st,
                "source": source,
            })
    print(f"{school_name}{year} (PDF): {len(out)} 个专业")
    return out


def main():
    import urllib3
    urllib3.disable_warnings()
    all_records = []
    scrapers = [
        ("南开大学2026", scrape_nankai_2026),
        ("南京大学AI2026", scrape_nju_ai_2026),
        ("厦门大学2026", scrape_xmu_2026),
        ("山东大学2026", scrape_sdu_2026),
        ("吉林大学2026", scrape_jlu_2026),
        ("大连理工大学2026", scrape_dlut_2026),
        ("北京理工大学2024", scrape_bit_2024),
        ("中山大学2025", scrape_sysu_2025),
        ("四川大学2025", scrape_scu_2025),
        ("中国科学技术大学2025", scrape_ustc_2025),
        ("同济大学2025", scrape_pdf_tongji_2025),
    ]
    for name, fn in scrapers:
        try:
            all_records += fn()
        except Exception as e:
            print(f"!! {name} 失败: {e}")
        time.sleep(1)

    # PDF - 湖南大学2025
    try:
        all_records += scrape_pdf(
            "https://csee.hnu.edu.cn/__local/5/E7/F2/947BFE7AF516BFD225D46636B14_C50FD87E_2F194.pdf",
            "湖南大学", "2025", "湖南大学信息科学与工程学院2025年复试成绩",
            major_col=3, score_col=7,
        )
    except Exception as e:
        print(f"!! 湖南大学2025 失败: {e}")
    time.sleep(1)

    # PDF - 兰州大学2025
    try:
        all_records += scrape_pdf(
            "https://xxxy.lzu.edu.cn/xxxynew/upload/files/20250322/cc8dc89e9b354ce294faec13d12f6b6b.pdf",
            "兰州大学", "2025", "兰州大学信息学院2025年复试名单",
            major_col=3, score_col=8,
        )
    except Exception as e:
        print(f"!! 兰州大学2025 失败: {e}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)
    print(f"\n共 {len(all_records)} 条记录 → {OUT}")
    for r in all_records:
        print(f"  {r['school_name']} {r['year']} {r['subject']}: "
              f"min={r['admit_min']} avg={r['admit_avg']} max={r['admit_max']} n={r['interview_count']}")


if __name__ == "__main__":
    main()
