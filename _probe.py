# -*- coding: utf-8 -*-
import re

h = open("dwzy.html", encoding="utf-8").read()
print("len:", len(h))
print("scripts:", sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', h))))
print("has 计算机科学与技术:", "计算机" in h)
# form model
m = re.search(r"form:\s*\{(.{0,500})", h, re.S)
print("form:", m.group(1)[:400] if m else "?")
for m in re.finditer(r"\.do['\"]", h):
    i = m.start()
    print("...", h[max(0, i-70):i+8].replace("\n", " ")[-75:])
