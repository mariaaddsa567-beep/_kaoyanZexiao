# -*- coding: utf-8 -*-
"""研招网（chsi）硕士专业目录：专业列表 -> 招生单位 -> 每校招生详情。"""
import time

from .http_client import Http, form_page

BASE = "https://yz.chsi.com.cn"
ZYS_URL = BASE + "/zsml/rs/zys.do"       # 按学科查专业条目
ZYDWS_URL = BASE + "/zsml/rs/zydws.do"   # 按专业查招生单位
YJFXS_URL = BASE + "/zsml/rs/yjfxs.do"   # 每校每专业的方向/科目/人数

# 计算机方向相关的一级学科 / 专业学位类别（工学 08）
DISCIPLINES = [
    ("0812", "计算机科学与技术"),
    ("0835", "软件工程"),
    ("0839", "网络空间安全"),
    ("0854", "电子信息"),  # 专业学位：计算机技术、人工智能、大数据等
]

# 主干专业代码（按学科）：登录墙下无法翻页取全招生单位，
# 改用「专业代码直查专业条目」+「专业+校名精确查招生单位」（均免翻页）
MAJOR_CORE = {
    "0812": ["081200"],
    "0835": ["083500"],
    "0839": ["083900"],
    "0854": ["085400", "085404", "085405", "085410", "085411", "085412"],
}


class LoginRequired(Exception):
    """研招网翻页需要登录（非限流，重试无效）。"""
    pass


class Chsi:
    def __init__(self, pacer=None, min_interval: float = 1.0):
        self.http = Http(
            BASE + "/zsml/",
            min_interval=min_interval,
            pacer=pacer,
        )

    def _post(self, url: str, form: dict, attempts: int = 8):
        """业务级重试：研招网限流时返回 {'msg':'参数错误','flag':false}。
        冷却窗内任何请求都会重置冷却，故失败后完全静默 300s 再试。
        若返回 {'msg':'请登录','flag':false}，说明需要登录才能翻页，直接抛 LoginRequired。"""
        import time as _t

        last = None
        for i in range(attempts):
            if i:
                _t.sleep(300)
                self.http.reset()
            d = self.http.post(url, data=form).json()
            if d.get("flag") or isinstance(d.get("msg"), dict):
                return d
            # "请登录" 不是限流，重试无效
            if isinstance(d.get("msg"), str) and "登录" in d["msg"]:
                raise LoginRequired(d["msg"])
            last = d
        raise RuntimeError(f"业务失败: {str(last)[:120]}")

    @staticmethod
    def _has_next(msg: dict, start: int, got: int) -> bool:
        """响应中无 nextPageAvailable 字段，须用 totalCount 判断是否还有下一页。"""
        try:
            total = int(msg.get("totalCount"))
        except (TypeError, ValueError):
            return False
        return start + got < total

    # 1) 一级学科 -> 专业代码条目（含自设专业；服务端固定每页 10 条，需翻页）
    def list_majors(self, yjxkdm: str) -> list[dict]:
        form = {
            "zydm": "", "zymc": "", "xwlx": "", "mldm": "08", "yjxkdm": yjxkdm,
            "xxfs": "", "tydxs": "", "jsggjh": "", "jsxbjh": "",
            "start": 0, "curPage": 1, "pageSize": 10,
        }
        out, start, page = [], 0, 1
        while True:
            try:
                d = self._post(ZYS_URL, {**form, "start": start, "curPage": page})
            except LoginRequired:
                break  # 翻页需登录，已取到的首页数据足够
            msg = d.get("msg") or {}
            items = msg.get("list") or []
            if not items:
                break
            for it in items:
                out.append({
                    "zydm": it["zydm"], "zymc": it["zymc"], "xwlx": it["xwlx"],
                    "mldm": it["mldm"], "mlmc": it.get("mlmc") or "工学",
                    "yjxkdm": it["yjxkdm"], "yjxkmc": it.get("yjxkmc") or "",
                    "sign": it["sign"],
                })
            if not msg.get("nextPageAvailable"):
                break
            start += int(msg.get("size") or len(items))
            page += 1
        # 登录墙截断/翻页结束后：按主干专业代码直查补充被截断的条目
        have = {m["zydm"] for m in out}
        for code in MAJOR_CORE.get(yjxkdm, []):
            try:
                d = self._post(ZYS_URL, {**form, "zydm": code})
            except LoginRequired:
                break
            msg = d.get("msg") or {}
            for it in (msg.get("list") or []):
                if it["zydm"] in have:
                    continue
                have.add(it["zydm"])
                out.append({
                    "zydm": it["zydm"], "zymc": it["zymc"], "xwlx": it["xwlx"],
                    "mldm": it["mldm"], "mlmc": it.get("mlmc") or "工学",
                    "yjxkdm": it["yjxkdm"], "yjxkmc": it.get("yjxkmc") or "",
                    "sign": it["sign"],
                })
        return out

    # 2) 专业 -> 招生单位（分页取全；翻页需登录，登录墙时截断为首页）
    def list_schools(self, major: dict, size: int = 50) -> list[dict]:
        base = {
            "zydm": major["zydm"], "zymc": major["zymc"],
            "xwlx": major["xwlx"], "mldm": major["mldm"], "yjxkdm": major["yjxkdm"],
            "xxfs": "", "tydxs": "", "jsggjh": "", "jsxbjh": "",
            "sign": major["sign"], "dwmc": "", "ssdm": "",
        }
        out, start, page = [], 0, 1
        while True:
            f = form_page(base, start, page, 10)  # 服务端固定每页 10 条
            try:
                d = self._post(ZYDWS_URL, f)
            except LoginRequired:
                break
            msg = d.get("msg") or {}
            lst = msg.get("list") or []
            out.extend(lst)
            if not lst or not self._has_next(msg, start, len(lst)):
                break
            start += int(msg.get("size") or len(lst))
            page += 1
        return out

    # 2b) 专业 + 校名精确查询（返回 0/1 条，无需翻页，可绕开登录墙）
    def school_by_name(self, major: dict, dwmc: str) -> list[dict]:
        base = {
            "zydm": major["zydm"], "zymc": major["zymc"],
            "xwlx": major["xwlx"], "mldm": major["mldm"], "yjxkdm": major["yjxkdm"],
            "xxfs": "", "tydxs": "", "jsggjh": "", "jsxbjh": "",
            "sign": major["sign"], "dwmc": dwmc, "ssdm": "",
        }
        f = form_page(base, 0, 1, 10)
        d = self._post(ZYDWS_URL, f)
        return (d.get("msg") or {}).get("list") or []

    # 3) 学校 x 专业 -> 方向/科目/人数（分页拉全，服务端固定每页 10 条）
    def school_major_detail(self, major: dict, sch: dict) -> list[dict]:
        base = {
            "zydm": major["zydm"], "zymc": major["zymc"],
            "dwdm": sch["dwdm"], "schId": sch.get("schId") or "",
            "sign": sch.get("sign") or major["sign"],
            "xxfs": "", "dwlxs": "all",
            "tydxs": "", "jsggjh": "", "jsxbjh": "",
        }
        out, start, page = [], 0, 1
        while True:
            f = form_page(base, start, page, 10)
            try:
                d = self._post(YJFXS_URL, f)
            except LoginRequired:
                break
            msg = d.get("msg") or {}
            if not isinstance(msg, dict):
                raise RuntimeError(str(msg))
            lst = msg.get("list") or []
            out.extend(lst)
            if not lst or not msg.get("nextPageAvailable"):
                break
            start += int(msg.get("size") or len(lst))
            page += 1
        return out


def collect(dwdm_filter: set[str] | None, progress_cb=None, min_interval: float = 2.5,
            workers: int = 2, sink_path: str | None = None, skip_pairs: set | None = None):
    """主采集流程（按专业条目并发，独立会话，共享全局限速）。
    dwdm_filter: 985/211 校名集合（归一化，None=不过滤）。
    sink_path: 增量落盘的 JSONL 文件（每完成一个专业条目追加）。
    skip_pairs: 跳过的 (dwdm, zydm) 集合（断点续跑）。"""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock, local
    import json as _json
    from .http_client import Pacer
    from .official_lists import normalize

    pacer = Pacer(min_interval)
    tl = local()
    lock = Lock()
    counter = {"done": 0, "recs": 0}
    sink = open(sink_path, "a", encoding="utf-8") if sink_path else None

    def get_chsi():
        if not hasattr(tl, "chsi"):
            tl.chsi = Chsi(pacer=pacer)
        return tl.chsi

    def log(msg):
        if progress_cb:
            with lock:
                progress_cb(msg)

    def process_major(major):
        chsi_c = get_chsi()
        out = []
        if major["zydm"] in MAJOR_CORE.get(major["yjxkdm"], []) and dwdm_filter:
            # 主干专业：逐校名精确查询（返回 0/1 条免翻页，绕开登录墙）
            schs, seen = [], set()
            for name in sorted(dwdm_filter):
                try:
                    found = chsi_c.school_by_name(major, name)
                except Exception as e:  # noqa: BLE001
                    log(f"!! 查询失败 {name} {major['zymc']}: {e}")
                    continue
                for sch in found:
                    if sch["dwdm"] in seen:
                        continue
                    seen.add(sch["dwdm"])
                    schs.append(sch)
        else:
            # 自设专业等：免登录只能取首页 10 条
            schs = chsi_c.list_schools(major)
        for sch in schs:
            if dwdm_filter and normalize(sch.get("dwmc") or "") not in dwdm_filter:
                continue
            if skip_pairs and (sch["dwdm"], major["zydm"]) in skip_pairs:
                continue
            try:
                details = chsi_c.school_major_detail(major, sch)
            except Exception as e:  # noqa: BLE001
                log(f"!! 失败 {sch.get('dwmc')} {major['zymc']}: {e}")
                details = []
            rec = {
                "major": major,
                "school": {
                    "dwdm": sch["dwdm"], "dwmc": sch["dwmc"],
                    "province": sch.get("szss") or "",
                    "zhx": sch.get("zhx") or "0",
                },
                "details": details,
            }
            out.append(rec)
            with lock:
                counter["done"] += 1
                counter["recs"] += 1
                n = counter["done"]
                if sink:
                    sink.write(_json.dumps(rec, ensure_ascii=False) + "\n")
                    sink.flush()
            if n % 25 == 0:
                log(f"已采集 {n} 组")
        return out

    # 1) 单会话先取各学科的专业条目列表（冷却自适应：失败自动 300s 退避）
    boot = Chsi(pacer=pacer)
    all_majors = []
    for yjxkdm, yjxkmc in DISCIPLINES:
        majors = boot.list_majors(yjxkdm)
        log(f"[{yjxkmc}] 专业条目 {len(majors)} 个")
        all_majors.append((yjxkmc, majors))

    result = []
    with ThreadPoolExecutor(workers) as ex:
        for yjxkmc, majors in all_majors:
            for recs in ex.map(process_major, majors):
                result.extend(recs)
                log(f"[{yjxkmc}] {recs[0]['major']['zymc'] if recs else '?'} 完成，"
                    f"本条 {len(recs)} 校，累计 {len(result)} 组")
    if sink:
        sink.close()
    return result
