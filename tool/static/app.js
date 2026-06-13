const RANGES = { "1Y": 365, "3Y": 365*3, "5Y": 365*5, "MAX": null };
let state = { range: "3Y", payload: null, charts: {} };

function showError(containerId, msg) {
  const el = document.getElementById(containerId);
  if (!el) return;
  // Dispose existing ECharts instance so a stale chart doesn't show
  if (state.charts[containerId]) {
    state.charts[containerId].dispose();
    delete state.charts[containerId];
  }
  el.innerHTML = `<div class="error-banner">数据获取失败：${msg || "未知错误"}</div>`;
}

// F&G 四象限天气读法（用户约定）：0-25 暴风雪 / 25-50 阴天 / 50-75 晴天 / 75-100 大太阳
const FNG_ZONE = v =>
  v < 25 ? { cls: "zone-fear",    desc: "❄️ 暴风雪" } :
  v < 50 ? { cls: "zone-caution", desc: "☁️ 阴天" } :
  v < 75 ? { cls: "zone-good",    desc: "🌤 晴天" } :
           { cls: "zone-greed",   desc: "☀️ 大太阳" };

// AAII 散户多空温度计：反向指标，极端值才有信号意义
const AAII_ZONE = s =>
  s > 20  ? { cls: "zone-caution", desc: "散户过热·反向偏空" } :
  s > 10  ? { cls: "zone-good",    desc: "散户偏多" } :
  s > -10 ? { cls: "zone-neutral", desc: "散户中性" } :
  s > -20 ? { cls: "zone-caution", desc: "散户偏空" } :
            { cls: "zone-fear",    desc: "散户过冷·反向偏多" };

const VIX_ZONE = v =>
  v < 12 ? { cls: "zone-greed",   desc: "极低" } :
  v < 15 ? { cls: "zone-good",    desc: "低" } :
  v < 20 ? { cls: "zone-neutral", desc: "中" } :
  v < 30 ? { cls: "zone-caution", desc: "偏高" } :
           { cls: "zone-fear",    desc: "恐慌" };

const BREADTH_ZONE = v =>
  v < 30 ? { cls: "zone-fear",    desc: "弱" } :
  v < 50 ? { cls: "zone-caution", desc: "偏弱" } :
  v < 70 ? { cls: "zone-neutral", desc: "中性" } :
           { cls: "zone-good",    desc: "强" };

const PC_ZONE = v =>
  v < 0.6 ? { cls: "zone-greed",   desc: "极乐观" } :
  v < 0.8 ? { cls: "zone-good",    desc: "乐观" } :
  v < 1.0 ? { cls: "zone-neutral", desc: "中性" } :
            { cls: "zone-fear",    desc: "悲观" };

// 市场温度计（复刻长桥）：温度高 = 估值贵 + 情绪亢奋 = 风险偏高（暖/热色警示），
// 温度低 = 便宜 + 情绪低迷 = 机会（冷色）。与 F&G 的"高=贪婪绿"语义相反。
const MTEMP_ZONE = v =>
  v < 20 ? { cls: "zone-good",    desc: "❄️ 冰点" } :
  v < 40 ? { cls: "zone-neutral", desc: "偏冷" } :
  v < 60 ? { cls: "zone-neutral", desc: "温和" } :
  v < 80 ? { cls: "zone-caution", desc: "偏热" } :
           { cls: "zone-fear",    desc: "🔥 过热" };
// 百分位 → 形容词（估值与情绪用不同措辞）
const pctWordVal = p => p < 20 ? "极低" : p < 40 ? "偏低" : p < 60 ? "中等" : p < 80 ? "偏高" : "极高";
const pctWordEmo = p => p < 20 ? "低迷" : p < 40 ? "偏冷" : p < 60 ? "中性" : p < 80 ? "偏暖" : "高涨";

// Token Expenditure Index has no canonical absolute bands — classify by
// trend vs the previous curated point. Rising = market paying up for
// frontier models (AI demand strong); falling = migration to cheap models.
// The curated series can lag reality: if a newer DOWNTREND milestone
// exists past the last hard point (reported decline whose absolute value
// wasn't published), surface that instead of the stale point-to-point trend.
const SDTOKEN_ZONE = d => {
  const history = d.history;
  if (!history || history.length < 2) return { cls: "zone-neutral", desc: "数据不足" };
  const last = history[history.length - 1];
  const ms = d.milestones || [];
  const lastMs = ms[ms.length - 1];
  if (lastMs && lastMs.date > last.date && /DOWNTREND/i.test(lastMs.note || "")) {
    return { cls: "zone-caution", desc: "报道转跌·官方未出值" };
  }
  const prev = history[history.length - 2].value;
  const pct = (last.value - prev) / prev * 100;
  return pct > 3  ? { cls: "zone-good",    desc: "付费意愿上行" } :
         pct < -3 ? { cls: "zone-caution", desc: "付费意愿回落" } :
                    { cls: "zone-neutral", desc: "停滞" };
};

function sliceSeries(series, days) {
  if (days === null) return series;
  if (!series || !series.length) return [];
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  return series.filter(p => p.date >= cutoffStr);
}

function renderOverview(ind) {
  const o = document.getElementById("overview");
  o.innerHTML = "";
  const lastDate = series => series && series.length ? series[series.length - 1].date : null;
  const items = [
    { key: "sdtoken", title: "Token 支出指数",
      get: d => d.status === "ok"
        ? { value: d.current.value.toFixed(2), zone: SDTOKEN_ZONE(d), date: d.current.date }
        : null },
    { key: "fng",     title: "Fear & Greed",
      get: d => d.status === "ok"
        ? { value: d.current.value.toFixed(0), zone: FNG_ZONE(d.current.value), date: lastDate(d.history) }
        : null },
    { key: "mtemp",   title: "市场温度",
      get: d => d.status === "ok"
        ? { value: d.current.value.toFixed(0) + "°", zone: MTEMP_ZONE(d.current.value), date: d.current.date }
        : null },
    { key: "vix",     title: "VIX",
      get: d => d.status === "ok"
        ? { value: d.current.value.toFixed(1), zone: VIX_ZONE(d.current.value), date: d.current.date }
        : null },
    { key: "aaii",    title: "AAII Bull-Bear",
      get: d => d.status === "ok"
        ? { value: (d.current.bullish - d.current.bearish).toFixed(1),
            zone: AAII_ZONE(d.current.bullish - d.current.bearish),
            date: d.current.date }
        : null },
    { key: "putcall", title: "Put/Call",
      get: d => d.status === "ok"
        ? { value: d.current.value.toFixed(2), zone: PC_ZONE(d.current.value), date: d.current.date }
        : null },
    { key: "breadth", title: "Breadth (NDX)",
      get: d => d.status === "ok"
        ? { value: d.current.ndx.toFixed(0) + "%", zone: BREADTH_ZONE(d.current.ndx), date: lastDate(d.ndx) }
        : null },
  ];
  for (const it of items) {
    const d = ind[it.key];
    const card = document.createElement("div");
    if (!d || d.status !== "ok") {
      card.className = "mini-card zone-error";
      card.innerHTML = `<div class="label">${it.title}</div>
        <div class="value">—</div><div class="desc">数据获取失败</div>`;
    } else {
      const v = it.get(d);
      const stale = d.stale_since_iso ? "·种子" : "";
      const dateLine = v.date ? `<div class="date">截至 ${v.date.slice(5)}${stale}</div>` : "";
      card.className = `mini-card ${v.zone.cls}`;
      card.innerHTML = `<div class="label">${it.title}</div>
        <div class="value">${v.value}</div><div class="desc">${v.zone.desc}</div>${dateLine}`;
    }
    o.appendChild(card);
  }
}

function getOrInitChart(id) {
  if (state.charts[id]) return state.charts[id];
  const c = echarts.init(document.getElementById(id));
  state.charts[id] = c;
  window.addEventListener("resize", () => c.resize());
  return c;
}

function setAsOf(spanId, dateStr, stale) {
  const el = document.getElementById(spanId);
  if (el && dateStr) el.textContent = dateStr + (stale ? "（种子数据）" : "");
}

function lineChartOption(title, series, refLines = [], colorBands = []) {
  return {
    grid: { left: 50, right: 24, top: 30, bottom: 40 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: series[0]?.data.map(p => p.date) ?? [] },
    yAxis: { type: "value", scale: true },
    series: series.map((s, i) => ({
      name: s.name,
      type: "line",
      data: s.data.map(p => p.value),
      smooth: true,
      symbol: "none",
      lineStyle: { width: 1.5 },
      markLine: i === 0 && refLines.length ? {
        symbol: "none", silent: true,
        data: refLines.map(r => ({ yAxis: r.y, label: { formatter: r.label }, lineStyle: { type: "dashed", color: "#9ca3af" } }))
      } : undefined,
      markArea: i === 0 && colorBands.length ? {
        silent: true,
        data: colorBands.map(b => [{ yAxis: b.from, itemStyle: { color: b.color } }, { yAxis: b.to }])
      } : undefined,
    })),
    legend: { top: 0, right: 0 },
  };
}

function renderFng(d) {
  if (d.status !== "ok") {
    showError("chart-fng-gauge", d.error_msg);
    showError("chart-fng-line", d.error_msg);
    return;
  }
  const sliced = sliceSeries(d.history, RANGES[state.range]);
  // Gauge
  const gauge = getOrInitChart("chart-fng-gauge");
  gauge.setOption({
    series: [{
      type: "gauge",
      startAngle: 200, endAngle: -20,
      min: 0, max: 100,
      axisLine: { lineStyle: { width: 18, color: [
        [0.25, "#ef4444"], [0.45, "#f59e0b"], [0.55, "#9ca3af"],
        [0.75, "#10b981"], [1, "#059669"]
      ] } },
      pointer: { width: 5 },
      detail: { formatter: "{value}", fontSize: 28, offsetCenter: [0, "70%"] },
      data: [{ value: d.current.value, name: FNG_ZONE(d.current.value).desc }],
      title: { offsetCenter: [0, "92%"], fontSize: 14 },
    }],
  });
  // Line — 色带按四象限划分
  const line = getOrInitChart("chart-fng-line");
  line.setOption(lineChartOption("F&G", [{ name: "F&G", data: sliced }],
    [{ y: 25, label: "25" }, { y: 50, label: "50" }, { y: 75, label: "75" }], [
      { from: 0, to: 25, color: "rgba(239,68,68,0.08)" },
      { from: 25, to: 50, color: "rgba(245,158,11,0.08)" },
      { from: 50, to: 75, color: "rgba(16,185,129,0.06)" },
      { from: 75, to: 100, color: "rgba(5,150,105,0.10)" },
    ]), true);
  setAsOf("fng-asof", d.history.length ? d.history[d.history.length - 1].date : null, !!d.stale_since_iso);
}

function renderMtemp(d) {
  if (d.status !== "ok") {
    showError("chart-mtemp-gauge", d.error_msg);
    showError("chart-mtemp-line", d.error_msg);
    return;
  }
  const sliced = sliceSeries(d.history, RANGES[state.range]);
  // Gauge — 冷(蓝)→热(红)，温度高=过热警示
  const gauge = getOrInitChart("chart-mtemp-gauge");
  gauge.setOption({
    series: [{
      type: "gauge",
      startAngle: 200, endAngle: -20,
      min: 0, max: 100,
      axisLine: { lineStyle: { width: 18, color: [
        [0.2, "#3b82f6"], [0.4, "#06b6d4"], [0.6, "#9ca3af"],
        [0.8, "#f59e0b"], [1, "#ef4444"]
      ] } },
      pointer: { width: 5 },
      detail: { formatter: "{value}°", fontSize: 28, offsetCenter: [0, "70%"] },
      data: [{ value: d.current.value, name: MTEMP_ZONE(d.current.value).desc }],
      title: { offsetCenter: [0, "92%"], fontSize: 14 },
    }],
  });
  // Line — 温度历史 + 色带（冷区蓝 / 热区橙红）
  const line = getOrInitChart("chart-mtemp-line");
  line.setOption(lineChartOption("市场温度", [{ name: "温度", data: sliced }],
    [{ y: 50, label: "50" }, { y: 80, label: "80" }], [
      { from: 0, to: 20, color: "rgba(59,130,246,0.08)" },
      { from: 60, to: 80, color: "rgba(245,158,11,0.08)" },
      { from: 80, to: 100, color: "rgba(239,68,68,0.10)" },
    ]), true);
  const asof = document.getElementById("mtemp-asof");
  if (asof) {
    const c = d.current;
    asof.textContent = `${c.date}${d.stale_since_iso ? "（种子数据）" : ""}`
      + ` · 估值 ${c.valuation_pct}（${pctWordVal(c.valuation_pct)}，PE ${c.pe}）`
      + ` · 情绪 ${c.emotion_pct}（${pctWordEmo(c.emotion_pct)}）`;
  }
}

function renderVix(d) {
  if (d.status !== "ok") {
    showError("chart-vix", d.error_msg);
    return;
  }
  const sliced = sliceSeries(d.history, RANGES[state.range]);
  const chart = getOrInitChart("chart-vix");
  chart.setOption(lineChartOption("VIX", [{ name: "VIX", data: sliced }],
    [{ y: 20, label: "20" }, { y: 30, label: "30" }],
    [
      { from: 0, to: 15, color: "rgba(5,150,105,0.06)" },
      { from: 20, to: 30, color: "rgba(245,158,11,0.06)" },
      { from: 30, to: 100, color: "rgba(239,68,68,0.06)" },
    ]), true);
  setAsOf("vix-asof", d.current.date, !!d.stale_since_iso);
}

function renderBreadth(d) {
  if (d.status !== "ok") {
    showError("chart-breadth", d.error_msg);
    return;
  }
  const ndx = sliceSeries(d.ndx, RANGES[state.range]);
  const spx = sliceSeries(d.spx, RANGES[state.range]);
  const chart = getOrInitChart("chart-breadth");
  chart.setOption(lineChartOption("Breadth",
    [{ name: "NDX 50DMA%", data: ndx }, { name: "SPX 50DMA%", data: spx }],
    [{ y: 50, label: "50%" }, { y: 70, label: "70%" }]), true);
  setAsOf("breadth-asof", d.ndx.length ? d.ndx[d.ndx.length - 1].date : null, !!d.stale_since_iso);
}

function renderAaii(d) {
  if (d.status !== "ok") {
    showError("chart-aaii", d.error_msg);
    return;
  }
  const chart = getOrInitChart("chart-aaii");
  chart.setOption(lineChartOption("AAII", [
    { name: "Bullish", data: sliceSeries(d.bullish, RANGES[state.range]) },
    { name: "Neutral", data: sliceSeries(d.neutral, RANGES[state.range]) },
    { name: "Bearish", data: sliceSeries(d.bearish, RANGES[state.range]) },
  ]), true);
  setAsOf("aaii-asof", d.current.date, !!d.stale_since_iso);
}

function renderPutCall(d) {
  if (d.status !== "ok") {
    showError("chart-putcall", d.error_msg);
    return;
  }
  const sliced = sliceSeries(d.history, RANGES[state.range]);
  const chart = getOrInitChart("chart-putcall");
  chart.setOption(lineChartOption("P/C", [{ name: "Put/Call", data: sliced }],
    [{ y: 0.7, label: "0.7" }, { y: 1.0, label: "1.0" }]), true);
  setAsOf("pc-asof", d.current.date, !!d.stale_since_iso);
}

function renderSdtoken(d) {
  if (d.status !== "ok") {
    showError("chart-sdtoken", d.error_msg);
    return;
  }
  // Curated series is sparse — slice only from 1Y down; 3Y/5Y/Max show all.
  const days = RANGES[state.range];
  const sliced = days !== null && days <= 365 ? sliceSeries(d.history, days) : d.history;
  const estimated = new Set(d.estimated_dates || []);
  const chart = getOrInitChart("chart-sdtoken");
  const option = lineChartOption("Token Index",
    [{ name: "USD / 1M tokens (加权)", data: sliced }]);
  // Sparse manual data: show each point; estimated points hollow + gray.
  option.series[0].symbol = "circle";
  option.series[0].symbolSize = 8;
  option.series[0].data = sliced.map(p => estimated.has(p.date)
    ? { value: p.value, symbol: "emptyCircle",
        itemStyle: { color: "#fff", borderColor: "#9ca3af", borderWidth: 2 } }
    : p.value);
  chart.setOption(option, true);
  const asof = document.getElementById("sdtoken-asof");
  if (asof) asof.textContent = `${d.current.date}（条目更新于 ${d.updated_at || "?"}）`;
}

function renderAll() {
  if (!state.payload) return;
  const ind = state.payload.indicators;
  renderOverview(ind);
  renderSdtoken(ind.sdtoken);
  renderFng(ind.fng);
  renderMtemp(ind.mtemp);
  renderVix(ind.vix);
  renderAaii(ind.aaii);
  renderPutCall(ind.putcall);
  renderBreadth(ind.breadth);
  const snapshotSuffix = window.__PRELOADED__ ? "（云端快照）" : "";
  document.getElementById("fetched-at").textContent =
    new Date(state.payload.fetched_at).toLocaleString("zh-CN") + snapshotSuffix;
}

async function loadData(force = false) {
  const url = force ? "/api/indicators?force=1" : "/api/indicators";
  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    state.payload = await r.json();
    renderAll();
  } catch (e) {
    document.getElementById("overview").innerHTML =
      `<div class="error-banner" style="grid-column: 1 / -1;">
        后端获取失败：${e.message}。请检查终端日志，然后点 ⟳ 重试。
      </div>`;
    document.getElementById("fetched-at").textContent = "失败";
    console.error("loadData failed", e);
  }
}

document.getElementById("range-picker").addEventListener("click", e => {
  if (e.target.tagName !== "BUTTON") return;
  for (const b of e.currentTarget.children) b.classList.remove("active");
  e.target.classList.add("active");
  state.range = e.target.dataset.range;
  renderAll();
});

document.getElementById("refresh-btn").addEventListener("click", () => loadData(true));

if (window.__PRELOADED__) {
  // Static snapshot mode (cloud-generated): data is baked in, no backend.
  document.getElementById("refresh-btn").style.display = "none";
  state.payload = window.__PRELOADED__;
  renderAll();
} else {
  loadData(false);
}
