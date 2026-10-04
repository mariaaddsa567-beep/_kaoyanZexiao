# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper import chsi
from scraper.http_client import form_page

c = chsi.Chsi(min_interval=2.0)

# zydws.do: 校名 + 一级学科，不带具体专业代码
base = {
    "dwmc": "北京大学", "ssdm": "", "mldm": "", "yjxkdm": "0812",
    "zydm": "", "zymc": "", "sign": "",
    "xwlx": "", "xxfs": "", "tydxs": "", "jsggjh": "", "jsxbjh": "",
}
f = form_page(base, 0, 1, 10)
try:
    d = c._post(chsi.ZYDWS_URL, f, attempts=2)
    msg = d.get("msg") or {}
    if isinstance(msg, dict):
        lst = msg.get("list") or []
        print("total:", msg.get("totalCount"), "got:", len(lst))
        for x in lst:
            print("  -", x.get("zydm"), x.get("zymc"), x.get("schId"), (x.get("sign") or "")[:10])
    else:
        print("ERR:", str(d)[:120])
except Exception as e:
    print("EXC:", str(e)[:120])
