# -*- coding: utf-8 -*-
"""推荐 API 冒烟测试。"""
import json
import urllib.request

profile = {
    "total": 330,
    "math_type": "数一",
    "english_type": "英一",
    "degree_pref": [],
    "provinces": [],
    "level_pref": ["985", "211"],
}
req = urllib.request.Request(
    "http://127.0.0.1:5000/api/recommend",
    data=json.dumps(profile).encode(),
    headers={"Content-Type": "application/json"}, method="POST")
d = json.loads(urllib.request.urlopen(req, timeout=30).read())
print("匹配报考点:", d.get("count"))
for t in ("冲", "稳", "保", "?"):
    arr = d["tiers"].get(t) or []
    print(f"\n[{t}] {len(arr)} 条")
    for r in arr[:3]:
        print(" ", r["school"], r["major_code"], "预测线", r["predict_line"],
              "prob", r["prob"], "conf", r["confidence"], r["note"][:18])
