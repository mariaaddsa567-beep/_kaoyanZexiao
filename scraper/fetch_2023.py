# -*- coding: utf-8 -*-
"""补充2023年国家线和34所自划线复试线公告到fsx.json。"""
import json
import os
import re
import time

import requests

BASE = "https://yz.chsi.com.cn"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE + "/",
}

# 2023年国家线（工学）—— 教育部官方数据
NATIONAL_2023 = [
    {"year": "2023", "category": "工学", "code": "08", "sub": "其他学科专业",
     "a_total": 273, "a1": 38, "a2": 57, "b_total": 263, "b1": 35, "b2": 53},
    {"year": "2023", "category": "工学", "code": "08", "sub": "工学照顾专业③",
     "a_total": 260, "a1": 35, "a2": 53, "b_total": 250, "b1": 32, "b2": 48},
]

# 2023年34所自划线公告URL（从研招网2023专题页解析）
ZHX_2023_URLS = {
    "北京大学": "/kyzx/fsfsx34/202303/20230311/2265499663.html",
    "中国人民大学": "/kyzx/fsfsx34/202303/20230317/2266967768.html",
    "清华大学": "/kyzx/fsfsx34/202303/20230311/2265499660.html",
    "北京航空航天大学": "/kyzx/fsfsx34/202303/20230316/2266235701.html",
    "北京理工大学": "/kyzx/fsfsx34/202303/20230318/2267101721.html",
    "中国农业大学": "/kyzx/fsfsx34/202303/20230315/2266234786.html",
    "北京师范大学": "/kyzx/fsfsx34/202303/20230316/2266427775.html",
    "南开大学": "/kyzx/fsfsx34/202303/20230315/2266235541.html",
    "天津大学": "/kyzx/fsfsx34/202303/20230315/2266235604.html",
    "大连理工大学": "/kyzx/fsfsx34/202303/20230316/2266634128.html",
    "东北大学": "/kyzx/fsfsx34/202303/20230314/2266099269.html",
    "吉林大学": "/kyzx/fsfsx34/202303/20230313/2265825311.html",
    "哈尔滨工业大学": "/kyzx/fsfsx34/202303/20230315/2266212073.html",
    "复旦大学": "/kyzx/fsfsx34/202303/20230317/2266827308.html",
    "同济大学": "/kyzx/fsfsx34/202303/20230313/2265794613.html",
    "上海交通大学": "/kyzx/fsfsx34/202303/20230313/2265890399.html",
    "南京大学": "/kyzx/fsfsx34/202303/20230315/2266212083.html",
    "东南大学": "/kyzx/fsfsx34/202303/20230316/2266235707.html",
    "浙江大学": "/kyzx/fsfsx34/202303/20230312/2265499675.html",
    "中国科学技术大学": "/kyzx/fsfsx34/202303/20230314/2266178284.html",
    "厦门大学": "/kyzx/fsfsx34/202303/20230315/2266234782.html",
    "山东大学": "/kyzx/fsfsx34/202303/20230314/2266180145.html",
    "武汉大学": "/kyzx/fsfsx34/202303/20230314/2266168872.html",
    "华中科技大学": "/kyzx/fsfsx34/202303/20230318/2267101711.html",
    "湖南大学": "/kyzx/fsfsx34/202303/20230316/2266235713.html",
    "中南大学": "/kyzx/fsfsx34/202303/20230315/2266234853.html",
    "中山大学": "/kyzx/fsfsx34/202303/20230312/2265499679.html",
    "华南理工大学": "/kyzx/fsfsx34/202303/20230312/2265499685.html",
    "四川大学": "/kyzx/fsfsx34/202303/20230314/2266099265.html",
    "重庆大学": "/kyzx/fsfsx34/202303/20230316/2266757324.html",
    "电子科技大学": "/kyzx/fsfsx34/202303/20230316/2266235695.html",
    "西安交通大学": "/kyzx/fsfsx34/202303/20230313/2265890389.html",
    "西北工业大学": "/kyzx/fsfsx34/202303/20230314/2266180138.html",
    "兰州大学": "/kyzx/fsfsx34/202303/20230315/2266234789.html",
}


def fetch_article(url):
    """获取公告页面，提取正文图片和PDF。"""
    full = url if url.startswith("http") else BASE + url
    r = requests.get(full, headers=H, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    html = r.text
    k = html.find('id="article_dnull"')
    body = html[k:] if k >= 0 else html
    body = body.split("近期热点")[0]
    imgs = re.findall(r'src="(https?://t\d+\.chei\.com\.cn/news/img/[^"]+)"', body)
    pdfs = re.findall(r'href="([^"]+\.pdf)"', body)
    return list(dict.fromkeys(imgs)), pdfs[0] if pdfs else ""


def main():
    path = os.path.join(DATA, "fsx.json")
    d = json.load(open(path, encoding="utf-8"))

    # ---- 1. 补充2023国家线 ----
    existing_years = {r["year"] for r in d["national"]}
    if "2023" not in existing_years:
        d["national"].extend(NATIONAL_2023)
        print(f"国家线: 补充2023年 {len(NATIONAL_2023)} 条")
    else:
        print("国家线: 2023年已存在，跳过")

    # ---- 2. 补充2023自划线公告 ----
    existing = {(z["school"], z["year"]) for z in d["zhx"]}
    added = 0
    for school, url in ZHX_2023_URLS.items():
        if (school, "2023") in existing:
            continue
        try:
            imgs, pdf = fetch_article(url)
            d["zhx"].append({
                "school": school, "year": "2023",
                "article_url": BASE + url,
                "imgs": imgs, "pdf": pdf,
            })
            added += 1
            print(f"自划线 {school} 2023: 图{len(imgs)} pdf={'Y' if pdf else '-'}")
            time.sleep(1.5)
        except Exception as e:
            print(f"!! {school} 2023 失败: {e}")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    print(f"\n完成：国家线 {len(d['national'])} 条；自划线公告 {len(d['zhx'])} 条（本次新增 {added}）")


if __name__ == "__main__":
    main()
