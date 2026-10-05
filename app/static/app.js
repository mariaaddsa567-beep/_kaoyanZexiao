/* 考研择校助手 v3 —— 408 专项重构：冲稳保推荐 / 院校库 / 志愿对比 */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const normName = (s) => String(s || "").replace(/（/g, "(").replace(/）/g, ")").replace(/\s/g, "");

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

let META = null;
let FAVS = JSON.parse(localStorage.getItem("favs") || "[]");

/* ---------- Tab 切换 ---------- */
document.querySelectorAll(".tab").forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-page").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    $(`tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "cmp") renderCompare();
  };
});

/* ---------- 冲稳保推荐 ---------- */
async function initProfile() {
  if (!META) return;
  $("pf-prov").innerHTML = `<option value="">不限</option>` +
    META.provinces.map(p => `<option>${esc(p)}</option>`).join("");
}

function collectProfile() {
  const provs = [...$("pf-prov").selectedOptions].map(o => o.value).filter(Boolean);
  const levels = [$("pf-lv985"), $("pf-lv211")].filter(c => c.checked).map(c => c.value);
  return {
    total: +$("pf-total").value || 0,
    math_type: $("pf-math").value,
    english_type: $("pf-english").value,
    degree_pref: [$("pf-degree").value].filter(Boolean),
    provinces: provs,
    level_pref: levels,
  };
}

function tierCard(r) {
  const confBadge = r.confidence === "A" ? '<span class="badge cA">置信A</span>'
    : r.confidence === "B" ? '<span class="badge cB">置信B·OCR</span>'
    : '<span class="badge cC">置信C·基准</span>';
  const trend = (r.trend || []).map(([y, v]) => `${y}:${v}`).join(" → ") || "暂无";
  const main = r.insufficient
    ? `区间 <b>${r.line_range[0]}~${r.line_range[1]}</b><span class="hint">（数据不足，不给具体概率）</span>`
    : `<b>${r.predict_line}</b>　你的差值 <b class="${r.diff >= 0 ? "up" : "down"}">${r.diff >= 0 ? "+" : ""}${r.diff}</b>　概率 <b>${r.prob}%</b>`;
  return `<div class="rec-card">
    <div class="rec-head">
      <b>${esc(r.school)}</b>
      <span class="badge">${esc(r.province)}</span>
      ${r.is_985 ? '<span class="badge">985</span>' : ""}${r.is_211 ? '<span class="badge">211</span>' : ""}
      ${r.sr_cs_rank ? `<span class="badge">学科排名${r.sr_cs_rank}</span>` : ""}
      ${confBadge}
      <button class="ghost fav-btn" data-dwdm="${r.dwdm}">☆收藏</button>
    </div>
    <div class="rec-meta">${esc(r.college)}｜${esc(r.major_name)}（${esc(r.major_code)}）｜${esc(r.degree_type)}｜名额 ${r.plan_total ?? "—"}</div>
    <div class="rec-line">${main}</div>
    <details><summary>为什么推荐 / 计算依据</summary>
      <ul>
        <li>预测依据：${esc(r.note)}；近三年线：${esc(trend)}</li>
        <li>σ=${r.sigma}（波动），模型：sigmoid((你的总分−预测线)/(σ/1.5))，规则 v1</li>
        ${r.risks.map(x => `<li class="risk">⚠ ${esc(x)}</li>`).join("")}
        ${r.plan_total <= 10 ? '<li class="risk">⚠ 名额少，推免占比未知，请核实该校推免名单</li>' : ""}
      </ul>
    </details>
  </div>`;
}

async function doRecommend() {
  $("rec-status").textContent = "计算中…";
  try {
    const d = await fetchJSON("/api/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectProfile()),
    });
    if (d.error) { $("rec-status").textContent = d.error; return; }
    $("rec-status").textContent = `共匹配 ${d.count} 个 408 报考点`;
    const sec = (t, arr, extra) => `<div class="tier"><h3 class="t-${t}">${t}${extra}</h3>
      ${arr.length ? arr.map(tierCard).join("") : '<p class="hint">暂无</p>'}</div>`;
    $("rec-result").innerHTML = `
      <div class="tiers">
        ${sec("冲", d.tiers["冲"], "（概率&lt;35%）")}${sec("稳", d.tiers["稳"], "（35%~70%）")}${sec("保", d.tiers["保"], "（≥70%）")}
      </div>
      ${d.tiers["?"].length ? sec("数据不足", d.tiers["?"], "") : ""}
      <p class="disclaimer">${esc(d.disclaimer)}</p>`;
    bindFav();
  } catch (e) {
    $("rec-status").textContent = "推荐失败：" + e.message;
  }
}

/* ---------- 院校库 ---------- */
async function loadSchools() {
  const p = new URLSearchParams({
    k: $("f-k").value.trim(), province: $("f-prov").value, tag: $("f-tag").value,
    group: $("f-group").value, subject408: $("f-408").value === "1" ? "1" : "",
    sort: $("f-sort").value,
  });
  try {
    const rows = await fetchJSON("/api/schools?" + p);
    $("grid").innerHTML = rows.map(cardHTML).join("") ||
      '<p class="hint">没有符合条件的院校</p>';
    bindFav();
  } catch (e) {
    $("grid").innerHTML = `<p class="hint">加载失败：${esc(e.message)}（请确认服务已启动）</p>`;
  }
}

function cardHTML(s) {
  return `<div class="card" data-dwdm="${s.dwdm}">
    <button class="fav-btn ${FAVS.includes(s.dwdm) ? "on" : ""}" data-dwdm="${s.dwdm}"
      title="加入对比">${FAVS.includes(s.dwdm) ? "★" : "☆"}</button>
    <h3>${esc(s.name)}</h3>
    <div class="meta">${esc(s.province)}｜${s.is_985 ? "985 " : ""}${s.is_211 ? "211 " : ""}${s.is_zhx ? "自划线" : ""}</div>
    <div class="meta">综合排名 ${s.sr_rank ?? "—"}｜计算机学科 ${s.sr_cs_rank ?? "—"}｜名额 ${s.quota ?? "—"}</div>
    ${s.has_408 ? '<span class="badge">408统考</span>' : ""}
  </div>`;
}

/* ---------- 详情弹层 ---------- */
let natLines = null;
async function fetchNatLines() {
  if (natLines) return natLines;
  try { natLines = await fetchJSON("/api/lines"); } catch (e) { return []; }
  return natLines;
}

function confBadge(c) {
  return c === "A" ? '<span class="badge cA">A·官方</span>'
    : c === "B" ? '<span class="badge cB">B·公告OCR</span>'
    : '<span class="badge cC">C·估算</span>';
}

function linesHTML(zhxLines, nat, scores) {
  let h = '<div class="sec-title">分数线参考</div>';
  if (scores && scores.length) {
    h += `<table class="fsx-table"><tr><th>年份</th><th>类型</th><th>线</th><th>单科</th><th>来源</th></tr>`;
    for (const r of scores) {
      h += `<tr><td>${esc(r.year)}</td><td>${r.scope === "school" ? "校线" : "国家线"} ${confBadge(r.confidence)}</td>
        <td><b>${r.initial_line ?? "—"}</b></td><td>${r.single1 ?? "—"}/${r.single2 ?? "—"}</td>
        <td class="src">${esc(r.source || "")}</td></tr>`;
    }
    h += "</table>";
  } else if (zhxLines && zhxLines.length) {
    h += '<p class="fsx-note">该校为 34 所自划线院校，复试基本分数线公告（分数表见图片，OCR 结构化数据整理中）：</p>';
    for (const z of zhxLines) {
      const imgs = (z.imgs || "").split("|").filter(Boolean);
      h += `<div class="zhx-year">${esc(z.year)} 年：
        <a href="${esc(z.article_url)}" target="_blank" rel="noopener">研招网公告原文</a></div>`;
      for (const u of imgs) h += `<img class="fsx-img" loading="lazy" src="${u}" alt="${esc(z.year)}复试线">`;
    }
  } else {
    h += '<p class="fsx-note">暂无校级线数据。计算机学硕（0812/0835/0839）与电子信息专硕（0854）执行工学国家线：</p>';
  }
  if ((!scores || !scores.some(s => s.scope === "national")) && nat && nat.length) {
    h += `<table class="fsx-table"><tr><th>年份</th><th>A区总分</th><th>A区单科</th><th>B区总分</th><th>B区单科</th></tr>`;
    for (const r of nat) h += `<tr><td>${esc(r.year)}</td><td><b>${r.a_total}</b></td>
      <td>${r.a1}/${r.a2}</td><td>${r.b_total}</td><td>${r.b1}/${r.b2}</td></tr>`;
    h += "</table>";
  }
  h += `<p class="fsx-note">注：单科为（满分=100 / 满分&gt;100）；实际院线可能高于校线。置信度：A=官方结构化，B=公告OCR识别，C=估算基准。</p>`;
  return h;
}

async function openDetail(dwdm) {
  const mask = $("modal-mask");
  mask.classList.remove("hidden");
  $("modal-body").innerHTML = '<p class="hint">加载中…</p>';
  try {
    const d = await fetchJSON(`/api/schools/${dwdm}`);
    const s = d.school;
    const progSec = (d.programs || []).length ? `
      <div class="sec-title">408 统考报考点</div>
      <table class="pg-table"><tr><th>学院</th><th>专业</th><th>学位</th><th>数学</th><th>英语</th><th>名额</th></tr>
      ${d.programs.filter(p => p.exam_type === "408").map(p => `<tr>
        <td>${esc(p.college)}</td><td>${esc(p.major_name)}</td><td>${esc(p.degree_type)}</td>
        <td>${esc(p.math_type) || "—"}</td><td>${esc(p.english_type) || "—"}</td>
        <td>${p.plan_total ?? "—"}</td></tr>`).join("")}</table>` : "";
    $("modal-body").innerHTML = `
      <h2>${esc(s.name)} <span class="code">(${s.dwdm})</span></h2>
      <div class="head-meta">${esc(s.province)}｜${esc(s.category)}｜
        ${s.is_985 ? "985 " : ""}${s.is_211 ? "211 " : ""}${s.is_zhx ? "自划线" : ""}｜综合排名 ${s.sr_rank ?? "—"}</div>
      ${progSec || "<p>无 408 统考报考点（可能有自命题，见下方专业列表）。</p>"}
      <details><summary>全部专业/科目明细（研招网目录）</summary>
        ${majorRows(d.majors || [])}
      </details>`;
    const nat = await fetchNatLines();
    $("modal-body").innerHTML += linesHTML(d.zhx_lines || [], nat, d.scores || []);
  } catch (e) {
    $("modal-body").innerHTML = `<p>加载失败：${esc(e.message)}。请确认已运行 python app/server.py。</p>`;
  }
}

function majorRows(ms) {
  if (!ms.length) return "<p>暂无数据</p>";
  return `<table class="pg-table"><tr><th>专业</th><th>学位</th><th>名额</th><th>科目组合</th><th>408</th></tr>
    ${ms.map(m => `<tr><td>${esc(m.zymc)}</td><td>${esc(m.xwlxmc)}</td>
      <td>${m.nzsrs_sum ?? "—"}</td><td class="src">${esc(m.kskm_set || "")}</td>
      <td>${m.has_408 ? "✓" : ""}</td></tr>`).join("")}</table>`;
}

/* ---------- 志愿对比 ---------- */
function saveFavs() {
  localStorage.setItem("favs", JSON.stringify(FAVS));
  $("fav-badge").textContent = FAVS.length || "";
}

function bindFav() {
  document.querySelectorAll(".fav-btn").forEach(b => {
    b.onclick = (ev) => {
      ev.stopPropagation();
      const id = b.dataset.dwdm;
      const i = FAVS.indexOf(id);
      if (i >= 0) FAVS.splice(i, 1);
      else if (FAVS.length >= 5) { alert("对比最多 5 所（文档 P0-5）"); return; }
      else FAVS.push(id);
      saveFavs();
      if ($("tab-lib").classList.contains("active")) loadSchools();
      if ($("tab-cmp").classList.contains("active")) renderCompare();
    };
  });
}

async function renderCompare() {
  if (!FAVS.length) { $("cmp-wrap").innerHTML = '<p class="hint">尚未添加对比院校。</p>'; return; }
  const details = await Promise.all(FAVS.map(id => fetchJSON(`/api/schools/${id}`).catch(() => null)));
  const ds = details.filter(Boolean);
  if (!ds.length) { $("cmp-wrap").innerHTML = '<p class="hint">数据加载失败</p>'; return; }
  const lineOf = (d) => {
    const best = (d.scores || []).filter(s => s.scope === "school").sort((a, b) => b.year.localeCompare(a.year))[0];
    return best ? `${best.year} 校线 ${best.initial_line}` : "—";
  };
  const row = (label, fn) => `<tr><th>${label}</th>${ds.map(fn).join("")}</tr>`;
  $("cmp-wrap").innerHTML = `<table class="cmp-table"><tbody>
    ${row("院校", d => `<td>${esc(d.school.name)}<br><button class="ghost" onclick="removeFav('${d.school.dwdm}')">移除</button></td>`)}
    ${row("省份/层次", d => `<td>${esc(d.school.province)}｜${d.school.is_985 ? "985" : d.school.is_211 ? "211" : ""}${d.school.is_zhx ? "·自划线" : ""}</td>`)}
    ${row("综合/学科排名", d => `<td>${d.school.sr_rank ?? "—"} / ${d.school.sr_cs_rank ?? "—"}</td>`)}
    ${row("408报考点数", d => `<td>${(d.programs || []).filter(p => p.exam_type === "408").length}</td>`)}
    ${row("总名额", d => `<td>${(d.programs || []).filter(p => p.exam_type === "408").reduce((a, p) => a + (p.plan_total || 0), 0) || "—"}</td>`)}
    ${row("最新校线", d => `<td>${lineOf(d)}</td>`)}
    ${row("国家线", d => `<td>${(natLines || []).length ? natLines.map(n => `${n.year}:${n.a_total}`).join("<br>") : "—"}</td>`)}
  </tbody></table>
  <p class="disclaimer">对比数据仅供参考，以院校官方公告为准。</p>`;
  bindFav();
}

window.removeFav = (id) => {
  FAVS = FAVS.filter(x => x !== id);
  saveFavs();
  renderCompare();
};

/* ---------- 初始化 ---------- */
async function init() {
  saveFavs();
  try {
    META = await fetchJSON("/api/meta");
    $("stats").textContent = `收录 ${META.stats.schools} 所院校 · 408 统考报考点 ${META.stats.programs408} 个 · 全部报考点 ${META.stats.programs_all} 个`;
    $("f-prov").innerHTML = '<option value="">全部省份</option>' +
      META.provinces.map(p => `<option>${esc(p)}</option>`).join("");
    initProfile();
  } catch (e) {
    $("stats").textContent = "服务未启动：请在项目目录运行  python app/server.py 后刷新";
    return;
  }
  loadSchools();
  $("btn-rec").onclick = doRecommend;
  $("f-k").oninput = loadSchools;
  ["f-prov", "f-tag", "f-group", "f-408", "f-sort"].forEach(id => { $(id).onchange = loadSchools; });
  $("modal-close").onclick = () => $("modal-mask").classList.add("hidden");
  $("modal-mask").onclick = (e) => { if (e.target.id === "modal-mask") $("modal-mask").classList.add("hidden"); };
  $("btn-cmp-clear").onclick = () => { FAVS = []; saveFavs(); renderCompare(); };
  $("grid").addEventListener("click", (e) => {
    const c = e.target.closest(".card");
    if (c && !e.target.classList.contains("fav-btn")) openDetail(c.dataset.dwdm);
  });
}

init();
