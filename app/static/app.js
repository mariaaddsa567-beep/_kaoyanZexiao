const GROUP_NAMES = { cs: "计算机科学与技术", se: "软件工程", cyb: "网络空间安全", xx: "电子信息" };
const $ = (id) => document.getElementById(id);
let debounceTimer = null;

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

function query() {
  const p = new URLSearchParams();
  const kw = $("f-kw").value.trim();
  const province = $("f-province").value;
  const tag = $("f-tag").value;
  const group = $("f-group").value;
  const sort = $("f-sort").value;
  const s408 = $("f-408").checked ? "1" : "";
  const xxfs = $("f-xxfs").checked ? "1" : "";
  if (kw) p.set("k", kw);
  if (province) p.set("province", province);
  if (tag !== "all") p.set("tag", tag);
  if (group) p.set("group", group);
  if (s408) p.set("subject408", s408);
  if (xxfs) p.set("xxfs", xxfs);
  p.set("sort", sort);
  return p.toString();
}

function tagHTML(s) {
  let h = "";
  if (s.is_985) h += '<span class="tag t985">985</span>';
  if (s.is_211) h += '<span class="tag t211">211</span>';
  if (s.is_zhx) h += '<span class="tag tzhx">自划线</span>';
  if (s.has_408) h += '<span class="tag t408">408 统考</span>';
  return h;
}

function rankHTML(s) {
  let h = "";
  if (s.sr_rank) h += `<span>综合 <b>${s.sr_rank}</b></span>`;
  if (s.sr_cs_rank) h += `<span>计算机学科 <b>${s.sr_cs_rank}</b></span>`;
  if (s.sr_se_rank) h += `<span>软件工程 <b>${s.sr_se_rank}</b></span>`;
  if (s.sr_cyb_rank) h += `<span>网安 <b>${s.sr_cyb_rank}</b></span>`;
  return h || "<span>—</span>";
}

function render(list) {
  const box = $("list");
  box.innerHTML = "";
  if (!list.length) { $("empty").classList.remove("hidden"); return; }
  $("empty").classList.add("hidden");
  for (const s of list) {
    const groups = (s.groups || "").split(",").filter(Boolean)
      .map((g) => GROUP_NAMES[g] || g).join(" / ");
    const div = document.createElement("div");
    div.className = "card";
    div.onclick = () => openDetail(s.dwdm);
    div.innerHTML = `
      <div class="top"><h3>${s.name}</h3><span class="code">${s.dwdm}</span></div>
      <div class="tags">${tagHTML(s)}</div>
      <div class="meta">
        地区：<b>${s.province || "—"}</b>｜类型：${s.category || "—"}<br>
        专业点：<b>${s.major_cnt}</b> 个｜拟招生：<b>${s.quota ?? "—"}</b> 人
        ${groups ? `<br>开设：${groups}` : ""}
      </div>
      <div class="ranks">${rankHTML(s)}</div>`;
    box.appendChild(div);
  }
}

async function load() {
  try {
    render(await fetchJSON("/api/schools?" + query()));
  } catch (e) {
    $("list").innerHTML = "";
    $("empty").textContent = "加载失败：" + e.message;
    $("empty").classList.remove("hidden");
  }
}

async function openDetail(dwdm) {
  const mask = $("modal-mask");
  mask.classList.remove("hidden");
  $("modal-body").innerHTML = "加载中…";
  try {
    var d = await fetchJSON("/api/schools/" + dwdm);
  } catch (e) {
    $("modal-body").innerHTML =
      "<h2>加载失败</h2><p style='margin:12px 0;color:#b91c1c'>" + e.message +
      "。若您是直接打开的本页文件，请先启动服务：" +
      "<code>python app/server.py</code>，再访问 http://127.0.0.1:5000</p>";
    return;
  }
  const s = d.school;
  const byMajor = {};
  for (const a of d.admissions) {
    (byMajor[a.zymc] ||= []).push(a);
  }
  let majorSec = "";
  for (const m of d.majors) {
    const rows = (byMajor[m.zymc] || [])
      .map((a) => `
        <tr>
          <td>${a.yxsmc || "—"}</td>
          <td>${a.yjfxmc || "—"}</td>
          <td>${a.nzsrsstr || a.nzsrs || "—"}</td>
          <td>${[a.km1, a.km2, a.km3, a.km4].filter(Boolean).join("<br>") || "—"}</td>
          <td>${a.zybz ? `<span class="bz">${a.zybz.replace(/\n/g, "；")}</span>` : ""}</td>
        </tr>`).join("");
    majorSec += `
      <div class="sec-title">${m.zymc}
        <span class="badge">${m.xwlxmc}</span>
        <span class="badge">${GROUP_NAMES[m.group_key] || ""}</span>
        ${m.has_408 ? '<span class="badge">含 408</span>' : ""}
      </div>
      <table>
        <tr><th>院系所</th><th>研究方向</th><th>拟招生</th><th>考试科目</th><th>备注</th></tr>
        ${rows}
      </table>`;
  }
  $("modal-body").innerHTML = `
    <h2>${s.name} <span class="code">(${s.dwdm})</span></h2>
    <div class="head-meta">
      ${s.province || "—"}｜${s.category || "—"}｜
      ${s.is_985 ? "985 " : ""}${s.is_211 ? "211 " : ""}${s.is_zhx ? "自划线" : ""}｜
      综合排名 ${s.sr_rank ?? "—"}
      ${s.sr_cs_rank ? `｜计算机学科排名 ${s.sr_cs_rank}` : ""}
    </div>
    ${majorSec || "<p>未收录该校计算机方向专业。</p>"}`;
  try {
    const nat = await fetchNatLines();
    $("modal-body").innerHTML += linesHTML(d.zhx_lines || [], nat);
  } catch (e) { /* 分数线加载失败不影响主体 */ }
}

let natLines = null;   // 工学国家线缓存

async function fetchNatLines() {
  if (natLines) return natLines;
  try {
    const d = await fetchJSON("/api/lines");
    natLines = d;  // 成功才缓存，失败下次重试
    return d;
  } catch (e) {
    return [];
  }
}

function linesHTML(zhxLines, nat) {
  let h = '<div class="sec-title">分数线参考</div>';
  if (zhxLines && zhxLines.length) {
    h += '<p class="fsx-note">该校为 34 所自划线院校，复试基本分数线公告如下（分数表见图片）：</p>';
    for (const z of zhxLines) {
      const imgs = (z.imgs || "").split("|").filter(Boolean);
      h += `<div class="zhx-year">${z.year} 年：
        <a href="${z.article_url}" target="_blank" rel="noopener">研招网公告原文</a>
        ${z.pdf ? `｜<a href="${z.pdf}" target="_blank" rel="noopener">PDF 下载</a>` : ""}</div>`;
      for (const u of imgs) {
        h += `<img class="fsx-img" loading="lazy" src="${u}" alt="${z.year}年复试分数线">`;
      }
    }
  } else {
    h += '<p class="fsx-note">该校执行国家线（非自划线）。计算机学硕（0812/0835/0839）与电子信息专硕（0854）均执行工学门类「其他学科专业」基本要求：</p>';
  }
  if (nat && nat.length) {
    h += `<table class="fsx-table">
      <tr><th>年份</th><th>A区总分</th><th>A区单科</th><th>B区总分</th><th>B区单科</th></tr>`;
    for (const r of nat) {
      h += `<tr><td>${r.year}</td><td><b>${r.a_total}</b></td><td>${r.a1} / ${r.a2}</td>
        <td>${r.b_total}</td><td>${r.b1} / ${r.b2}</td></tr>`;
    }
    h += `</table><p class="fsx-note">注：单科为（满分=100 / 满分&gt;100）；自划线校院系线、非自划线校实际复试线可能高于上述基本要求。</p>`;
  }
  return h;
}

function bindEvents() {
  $("f-kw").addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(load, 300);
  });
  for (const id of ["f-province", "f-tag", "f-group", "f-sort", "f-408", "f-xxfs"]) {
    $(id).addEventListener("change", load);
  }
  $("btn-reset").onclick = () => {
    $("f-kw").value = ""; $("f-province").value = ""; $("f-tag").value = "all";
    $("f-group").value = ""; $("f-sort").value = "sr_rank";
    $("f-408").checked = false; $("f-xxfs").checked = false;
    load();
  };
  $("modal-close").onclick = () => $("modal-mask").classList.add("hidden");
  $("modal-mask").addEventListener("click", (e) => {
    if (e.target === $("modal-mask")) $("modal-mask").classList.add("hidden");
  });
}

async function init() {
  bindEvents();
  if (location.protocol === "file:") {
    $("empty").textContent =
      "本页面需要通过服务访问：先运行 python app/server.py，再用浏览器打开 http://127.0.0.1:5000";
    $("empty").classList.remove("hidden");
    return;
  }
  try {
    const meta = await fetchJSON("/api/meta");
    for (const p of meta.provinces) {
      const o = document.createElement("option");
      o.value = p; o.textContent = p;
      $("f-province").appendChild(o);
    }
    $("stats").textContent =
      `${meta.stats.schools} 所院校 · ${meta.stats.points} 个专业点 · 拟招生 ${meta.stats.quota ?? "—"} 人`;
  } catch (e) { /* 数据库未就绪时静默 */ }
  load();
}

init();
