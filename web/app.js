/**
 * NDX Quantitative Strategy — Institutional Terminal Application
 * Features:
 *  - Real-time Telemetry & Market Status Clock
 *  - Dual Strategy Model Simulation & Side-by-Side Overlay
 *  - Institutional Quant Performance & Risk Metrics (Sharpe, Sortino, Calmar, CAGR)
 *  - Annual Performance & Crisis Alpha Matrix (2010–2026)
 *  - Interactive Drawdown & Underwater Profile Visualizer
 *  - Forward-Looking Trigger Radar with Next-Session Thresholds
 *  - Completed Round-Trip Trade Inspector & Raw Fill Explorer
 *  - One-Click CSV Export & Deep-Linking Shareable URL State
 */

// App State
let currentTab = "equity";
let currentTimeframe = "ALL";
let currentModel = "symmetric_atr";
let currentTradeView = "cycles"; // 'cycles' or 'executions'
let currentMatrixView = "all";   // 'all' or 'crisis'
let overlayBothModels = true;
let simulatedCapital = 10000;
let cachedData = null;
let chartInstance = null;
let autoRefreshTimer = null;

// Custom Date Range & Strategy Sandbox State
let customStartDate = "2015-01-01";
let customEndDate = "2026-03-30";
let sandboxCustomModelResult = null;
let sbPreviewChartInstance = null;

// Real-time Clock interval
setInterval(updateClocks, 1000);

document.addEventListener("DOMContentLoaded", () => {
  parseUrlParams();
  initEventListeners();
  fetchDashboardData();
  startAutoRefresh();
});

/* ==========================================================================
   URL PARAMETERS & DEEP LINKING
   ========================================================================== */
function parseUrlParams() {
  const params = new URLSearchParams(window.location.search);

  if (params.has("model")) {
    const m = params.get("model");
    if (m === "symmetric_atr" || m === "original_agile") {
      currentModel = m;
      document.querySelectorAll(".model-toggle-btn").forEach(b => {
        b.classList.toggle("active", b.getAttribute("data-model") === m);
      });
    }
  }

  if (params.has("cap")) {
    const c = parseFloat(params.get("cap"));
    if (!isNaN(c) && c > 0) {
      simulatedCapital = c;
      const inp = document.getElementById("simCustomCapital");
      if (inp) inp.value = c;
      document.querySelectorAll(".sim-btn").forEach(b => {
        b.classList.toggle("active", parseFloat(b.getAttribute("data-amt")) === c);
      });
    }
  }

  if (params.has("tf")) {
    const tf = params.get("tf").toUpperCase();
    if (["1M", "6M", "1Y", "5Y", "2022", "2020", "ALL", "CUSTOM"].includes(tf)) {
      currentTimeframe = tf;
      document.querySelectorAll(".tf-btn").forEach(b => {
        b.classList.toggle("active", b.getAttribute("data-tf") === tf);
      });
      if (tf === "CUSTOM") {
        const bar = document.getElementById("customRangeBar");
        if (bar) bar.style.display = "block";
      }
    }
  }

  if (params.has("c_start")) {
    customStartDate = params.get("c_start");
    const el = document.getElementById("customStartDate");
    if (el) el.value = customStartDate;
  }
  if (params.has("c_end")) {
    customEndDate = params.get("c_end");
    const el = document.getElementById("customEndDate");
    if (el) el.value = customEndDate;
  }

  if (params.has("tab")) {
    const tb = params.get("tab").toLowerCase();
    if (["equity", "technicals", "rsi", "drawdown"].includes(tb)) {
      currentTab = tb;
      document.querySelectorAll(".tab-btn").forEach(b => {
        b.classList.toggle("active", b.getAttribute("data-tab") === tb);
      });
    }
  }

  if (params.has("tradeview")) {
    const tv = params.get("tradeview").toLowerCase();
    if (["cycles", "executions"].includes(tv)) {
      currentTradeView = tv;
      document.querySelectorAll(".tview-btn").forEach(b => {
        b.classList.toggle("active", b.getAttribute("data-view") === tv);
      });
    }
  }
}

function updateUrlParams() {
  const url = new URL(window.location);
  url.searchParams.set("model", currentModel);
  url.searchParams.set("cap", simulatedCapital);
  url.searchParams.set("tf", currentTimeframe);
  url.searchParams.set("tab", currentTab);
  url.searchParams.set("tradeview", currentTradeView);
  if (currentTimeframe === "CUSTOM") {
    url.searchParams.set("c_start", customStartDate);
    url.searchParams.set("c_end", customEndDate);
  } else {
    url.searchParams.delete("c_start");
    url.searchParams.delete("c_end");
  }
  window.history.replaceState({}, "", url);
}

function showToast(message, icon = "fa-solid fa-check text-emerald") {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = `<i class="${icon}"></i> <span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

/* ==========================================================================
   EVENT LISTENERS INITIALIZATION
   ========================================================================== */
function initEventListeners() {
  // Strategy Model selector buttons
  document.querySelectorAll(".model-toggle-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".model-toggle-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentModel = btn.getAttribute("data-model");
      updateUrlParams();
      if (cachedData) {
        renderUI(cachedData);
        renderChart();
      }
    });
  });

  // Model compare checkbox
  const chkCompare = document.getElementById("chkCompareModels");
  if (chkCompare) {
    chkCompare.addEventListener("change", (e) => {
      overlayBothModels = e.target.checked;
      renderChart();
    });
  }

  // Tabs switching
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentTab = btn.getAttribute("data-tab");
      updateUrlParams();
      renderChart();
    });
  });

  // Timeframe buttons & Custom Range Bar Toggle
  document.querySelectorAll(".tf-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const tf = btn.getAttribute("data-tf");
      const customBar = document.getElementById("customRangeBar");
      
      if (tf === "CUSTOM") {
        const isCurrentlyVisible = customBar && customBar.style.display !== "none";
        if (isCurrentlyVisible && currentTimeframe === "CUSTOM") {
          // Toggle off -> revert to ALL
          if (customBar) customBar.style.display = "none";
          document.querySelectorAll(".tf-btn").forEach(b => b.classList.toggle("active", b.getAttribute("data-tf") === "ALL"));
          currentTimeframe = "ALL";
        } else {
          if (customBar) customBar.style.display = "block";
          document.querySelectorAll(".tf-btn").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          currentTimeframe = "CUSTOM";
        }
      } else {
        if (customBar) customBar.style.display = "none";
        document.querySelectorAll(".tf-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        currentTimeframe = tf;
      }
      
      updateUrlParams();
      if (cachedData) {
        renderQuantMetrics(cachedData);
        renderChart();
      }
    });
  });

  // Custom Date Range Apply Button
  const btnApplyRange = document.getElementById("btnApplyCustomRange");
  if (btnApplyRange) {
    btnApplyRange.addEventListener("click", () => {
      const s = document.getElementById("customStartDate").value;
      const e = document.getElementById("customEndDate").value;
      if (!s || !e) {
        showToast("Please select valid start and end dates.", "fa-solid fa-triangle-exclamation text-amber");
        return;
      }
      if (s > e) {
        showToast("Start date must be before or equal to end date.", "fa-solid fa-triangle-exclamation text-rose");
        return;
      }
      customStartDate = s;
      customEndDate = e;
      currentTimeframe = "CUSTOM";
      document.querySelectorAll(".tf-btn").forEach(b => b.classList.toggle("active", b.getAttribute("data-tf") === "CUSTOM"));
      updateUrlParams();
      if (cachedData) {
        renderQuantMetrics(cachedData);
        renderChart();
        showToast(`Applied custom window: ${s} to ${e}`);
      }
    });
  }

  // Custom Date Range Reset Button
  const btnResetRange = document.getElementById("btnResetCustomRange");
  if (btnResetRange) {
    btnResetRange.addEventListener("click", () => {
      currentTimeframe = "ALL";
      const customBar = document.getElementById("customRangeBar");
      if (customBar) customBar.style.display = "none";
      document.querySelectorAll(".tf-btn").forEach(b => b.classList.toggle("active", b.getAttribute("data-tf") === "ALL"));
      updateUrlParams();
      if (cachedData) {
        renderQuantMetrics(cachedData);
        renderChart();
        showToast("Reset to full 16-year timeline.");
      }
    });
  }

  // Quick Eras preset buttons in Date Range Bar
  document.querySelectorAll(".range-preset-tag").forEach(btn => {
    btn.addEventListener("click", () => {
      const s = btn.getAttribute("data-start");
      const e = btn.getAttribute("data-end");
      if (s && e) {
        customStartDate = s;
        customEndDate = e;
        const inpS = document.getElementById("customStartDate");
        const inpE = document.getElementById("customEndDate");
        if (inpS) inpS.value = s;
        if (inpE) inpE.value = e;
        currentTimeframe = "CUSTOM";
        document.querySelectorAll(".tf-btn").forEach(b => b.classList.toggle("active", b.getAttribute("data-tf") === "CUSTOM"));
        updateUrlParams();
        if (cachedData) {
          renderQuantMetrics(cachedData);
          renderChart();
          showToast(`Loaded era: ${btn.textContent.trim()}`);
        }
      }
    });
  });

  // Quant Lab Sandbox Modal Event Handlers
  const btnOpenSandbox = document.getElementById("btnOpenSandbox");
  const sandboxModal = document.getElementById("sandboxModalBackdrop");
  const btnCloseSandbox = document.getElementById("btnCloseSandbox");
  
  if (btnOpenSandbox && sandboxModal) {
    btnOpenSandbox.addEventListener("click", () => {
      sandboxModal.style.display = "flex";
      document.body.style.overflow = "hidden";
      runClientSideSimulation();
    });
  }
  
  if (btnCloseSandbox && sandboxModal) {
    btnCloseSandbox.addEventListener("click", () => {
      sandboxModal.style.display = "none";
      document.body.style.overflow = "";
    });
  }

  if (sandboxModal) {
    sandboxModal.addEventListener("click", (e) => {
      if (e.target === sandboxModal) {
        sandboxModal.style.display = "none";
        document.body.style.overflow = "";
      }
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && sandboxModal && sandboxModal.style.display !== "none") {
      sandboxModal.style.display = "none";
      document.body.style.overflow = "";
    }
  });

  // Sandbox SMA Slider Display listener
  const sbSmaSlider = document.getElementById("sbSmaPeriod");
  const sbSmaDisplay = document.getElementById("sbSmaDisplay");
  if (sbSmaSlider && sbSmaDisplay) {
    sbSmaSlider.addEventListener("input", (e) => {
      sbSmaDisplay.textContent = `${e.target.value} Days`;
    });
  }

  // Sandbox Capital Pills
  document.querySelectorAll(".sb-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".sb-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      const amt = pill.getAttribute("data-amt");
      const sbCapInp = document.getElementById("sbCapital");
      if (sbCapInp && amt) sbCapInp.value = amt;
    });
  });

  // Run Simulation Button
  const btnRunSandbox = document.getElementById("btnRunSandbox");
  if (btnRunSandbox) {
    btnRunSandbox.addEventListener("click", runClientSideSimulation);
  }

  // Overlay on Main Chart Button
  const btnOverlaySandbox = document.getElementById("btnOverlaySandboxOnMain");
  if (btnOverlaySandbox) {
    btnOverlaySandbox.addEventListener("click", () => {
      if (!window._lastSandboxResult) {
        runClientSideSimulation();
      }
      if (window._lastSandboxResult) {
        sandboxCustomModelResult = window._lastSandboxResult;
        if (sandboxModal) {
          sandboxModal.style.display = "none";
          document.body.style.overflow = "";
        }
        currentTab = "equity";
        document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.getAttribute("data-tab") === "equity"));
        updateUrlParams();
        renderChart();
        showToast(`"${sandboxCustomModelResult.name}" overlaid on main chart!`, "fa-solid fa-layer-group text-amber");
      }
    });
  }

  // Export Sandbox Simulation CSV Button
  const btnExportSandbox = document.getElementById("btnExportSandboxCsv");
  if (btnExportSandbox) {
    btnExportSandbox.addEventListener("click", exportSandboxCsv);
  }

  // Clear Overlay Click Delegator
  document.addEventListener("click", (e) => {
    if (e.target && e.target.id === "btnClearSandboxOverlay") {
      e.preventDefault();
      sandboxCustomModelResult = null;
      renderChart();
      showToast("Custom sandbox overlay removed from chart.");
    }
  });

  // Trade Table Filter Controls
  const actionFilter = document.getElementById("tradeActionFilter");
  if (actionFilter) actionFilter.addEventListener("change", applyTradeFilters);

  const yearFilter = document.getElementById("tradeYearFilter");
  if (yearFilter) yearFilter.addEventListener("change", applyTradeFilters);

  const searchInput = document.getElementById("tradeSearchInput");
  if (searchInput) searchInput.addEventListener("input", applyTradeFilters);

  // Copy log button
  const copyBtn = document.getElementById("btnCopyLog");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      if (!cachedData || !cachedData.recent_logs) return;
      const text = cachedData.recent_logs.join("\n");
      navigator.clipboard.writeText(text).then(() => {
        copyBtn.innerHTML = '<i class="fa-solid fa-check text-emerald"></i>';
        setTimeout(() => copyBtn.innerHTML = '<i class="fa-regular fa-copy"></i>', 1500);
      });
    });
  }
}

function startAutoRefresh() {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer);
  autoRefreshTimer = setInterval(() => {
    fetchDashboardData(true);
  }, 10000);
}

async function fetchDashboardData(isBackground = false) {
  try {
    const isLocal = window.location.port === "5050" || window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
    let endpoint = isLocal ? "/api/data" : "./data.json";
    let res = await fetch(endpoint + "?_t=" + Date.now());
    if (!res.ok && isLocal) {
      // Fallback to local static data.json if running simple static HTTP server
      endpoint = "./data.json";
      res = await fetch(endpoint + "?_t=" + Date.now());
    }
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    cachedData = data;
    renderUI(data);
    renderChart();
  } catch (err) {
    console.error("Failed to fetch dashboard data:", err);
  }
}

/* ==========================================================================
   UI RENDERING MASTER
   ========================================================================== */
function renderUI(data) {
  const modelObj = (data.models && data.models[currentModel]) ? data.models[currentModel] : data;
  const p = modelObj.portfolio || data.portfolio;
  const stats = modelObj.stats || data.stats;
  const daily = modelObj.daily_summary || data.daily_summary;

  const baseStartCap = p.starting_capital || 10000;
  const scaleFactor = simulatedCapital / baseStartCap;

  // 1. Header Market Status & Clock
  updateMarketStatus();

  // 2. Regime Hero Banner
  const banner = document.getElementById("regimeBanner");
  const badge = document.getElementById("regimeBadge");
  const badgeText = document.getElementById("regimeBadgeText");
  const headline = document.getElementById("regimeHeadline");
  const reason = document.getElementById("regimeReason");
  const icon = document.getElementById("regimeIcon");

  if (p.position === "TQQQ_100") {
    banner.className = "regime-hero-banner regime-bull";
    badge.className = "regime-badge badge-bull";
    badgeText.textContent = "100% TQQQ (BULL TREND)";
    headline.textContent = "Full Bull Regime Confirmed";
    icon.className = "fa-solid fa-bolt-lightning";
  } else if (p.position === "TQQQ_50") {
    banner.className = "regime-hero-banner regime-bull";
    badge.className = "regime-badge badge-bull";
    badgeText.textContent = "50% TQQQ (TRIMMED)";
    headline.textContent = "Cautious Bull Exposure (Divergence Trim)";
    icon.className = "fa-solid fa-triangle-exclamation";
  } else if (p.position === "TQQQ_30") {
    banner.className = "regime-hero-banner regime-bear";
    badge.className = "regime-badge badge-bear";
    badgeText.textContent = "30% TQQQ (DEFENSIVE)";
    headline.textContent = "Overbought Momentum Trim Active";
    icon.className = "fa-solid fa-shield-halved";
  } else if (p.position === "SQQQ") {
    banner.className = "regime-hero-banner regime-bear";
    badge.className = "regime-badge badge-bear";
    badgeText.textContent = "100% SQQQ (BEAR SHORT)";
    headline.textContent = "Active Short Regime (Price < SMA50 & SMA250)";
    icon.className = "fa-solid fa-arrow-down-trend-spread";
  } else {
    banner.className = "regime-hero-banner regime-cash";
    badge.className = "regime-badge badge-cash";
    badgeText.textContent = "100% CASH (DEFENSIVE)";
    headline.textContent = "Capital Preservation Mode";
    icon.className = "fa-solid fa-piggy-bank";
  }
  reason.textContent = p.last_signal || "System executing systematic rules.";

  // Safety margins
  document.getElementById("distSma50Text").textContent = `${stats.dist_sma50_pts >= 0 ? '+' : ''}${stats.dist_sma50_pts.toFixed(1)} pts (${stats.dist_sma50_pct >= 0 ? '+' : ''}${stats.dist_sma50_pct.toFixed(2)}%)`;
  const distRsi = (75 - stats.rsi).toFixed(1);
  document.getElementById("distRsiText").textContent = distRsi > 0 ? `${distRsi} pts` : "OVERBOUGHT";

  // 3. Scaled KPI Cards
  const scaledTotal = p.total_value * scaleFactor;
  const scaledPnl = (p.total_value - baseStartCap) * scaleFactor;
  const pnlPct = ((p.total_value / baseStartCap) - 1) * 100;

  document.getElementById("totalValue").textContent = formatCurrency(scaledTotal);
  const pnlPill = document.getElementById("pnlPill");
  pnlPill.className = `pnl-pill ${scaledPnl >= 0 ? "positive" : "negative"}`;
  pnlPill.textContent = `${scaledPnl >= 0 ? "+" : ""}${formatCurrency(scaledPnl)} (${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%)`;
  document.getElementById("startingCapText").textContent = `Base: $${simulatedCapital.toLocaleString()}`;

  // Simulator Result Badge
  const simValEl = document.getElementById("simResultValue");
  if (simValEl) simValEl.textContent = formatCurrency(scaledTotal);

  // Holdings Card
  const holdingsTitle = document.getElementById("holdingsTitle");
  const holdingsShares = document.getElementById("holdingsShares");
  const holdingsCost = document.getElementById("holdingsCost");
  if (p.tqqq_shares > 0) {
    holdingsTitle.textContent = `${(p.allocation_pct * 100).toFixed(0)}% TQQQ`;
    holdingsShares.textContent = `${(p.tqqq_shares * scaleFactor).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} shares`;
    holdingsCost.textContent = `Avg Cost: $${p.tqqq_avg_cost.toFixed(2)}`;
  } else if (p.sqqq_shares > 0) {
    holdingsTitle.textContent = "100% SQQQ";
    holdingsShares.textContent = `${(p.sqqq_shares * scaleFactor).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} shares`;
    holdingsCost.textContent = `Avg Cost: $${p.sqqq_avg_cost.toFixed(2)}`;
  } else {
    holdingsTitle.textContent = "100% Cash";
    holdingsShares.textContent = formatCurrency(p.cash * scaleFactor);
    holdingsCost.textContent = "4.5% Risk-Free Accrual";
  }

  // Market & Technicals Cards
  const latestDaily = (daily && daily.length > 0) ? daily[daily.length - 1] : {};
  const curNdx = (stats && stats.ndx_price) || latestDaily.ndx_price || 0;
  const curSma50 = (stats && stats.sma50) || latestDaily.sma50 || 0;
  const curSma250 = (stats && stats.sma250) || latestDaily.sma250 || 0;
  const curRsi = (stats && stats.rsi !== undefined) ? stats.rsi : (latestDaily.rsi !== undefined ? latestDaily.rsi : 50.0);

  const ndxEl = document.getElementById("ndxLevel");
  if (ndxEl) ndxEl.textContent = curNdx ? curNdx.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "--";

  const sma50El = document.getElementById("ndxSma50");
  if (sma50El) sma50El.textContent = curSma50 ? `SMA50: ${curSma50.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}` : "SMA50: --";

  const sma250El = document.getElementById("ndxSma250");
  if (sma250El) sma250El.textContent = curSma250 ? `SMA250: ${curSma250.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}` : "SMA250: --";

  const rsiEl = document.getElementById("rsiValue");
  if (rsiEl) rsiEl.textContent = typeof curRsi === "number" ? curRsi.toFixed(1) : "--";

  const rsiBadge = document.getElementById("rsiZoneBadge");
  if (rsiBadge) {
    if (curRsi >= 75) {
      rsiBadge.textContent = "OVERBOUGHT";
      rsiBadge.style.color = "#F43F5E";
      rsiBadge.style.background = "rgba(244, 63, 94, 0.15)";
    } else if (curRsi <= 30) {
      rsiBadge.textContent = "OVERSOLD";
      rsiBadge.style.color = "#00F2FE";
      rsiBadge.style.background = "rgba(0, 242, 254, 0.15)";
    } else {
      rsiBadge.textContent = "NEUTRAL";
      rsiBadge.style.color = "#00E676";
      rsiBadge.style.background = "rgba(0, 230, 118, 0.15)";
    }
  }

  // 4. Institutional Quant Risk & Quality Metrics
  renderQuantMetrics(data);

  // 5. Forward Trigger Radar
  renderTriggerRadar(data);

  // 6. Annual Performance & Crisis Alpha Matrix
  renderAnnualMatrix(data);

  // 7. Telemetry Sidebar Gauges
  renderSidebarTelemetry(data, scaleFactor);

  // 8. Trade Table / Round-Trip Inspector
  renderTradesTable(modelObj.trades || data.trades);

  // 9. Strategy Log Terminal
  renderTerminal(modelObj.recent_logs || data.recent_logs);
}

/* ==========================================================================
   1. INSTITUTIONAL QUANT METRICS CALCULATOR & RENDERER
   ========================================================================== */
function renderQuantMetrics(data) {
  const modelObj = (data.models && data.models[currentModel]) ? data.models[currentModel] : data;
  let daily = modelObj.daily_summary ? [...modelObj.daily_summary] : [...(data.daily_summary || [])];
  let trades = modelObj.trades ? [...modelObj.trades] : [...(data.trades || [])];

  if (!daily || daily.length < 2) return;

  // Dynamic window filtering based on active timeframe or custom dates
  let windowTitle = "Full 16-Year Audit (2010–2026)";
  if (currentTimeframe === "1M") {
    daily = daily.slice(-22);
    windowTitle = `1-Month Window (${daily[0].date} to ${daily[daily.length - 1].date})`;
  } else if (currentTimeframe === "6M") {
    daily = daily.slice(-126);
    windowTitle = `6-Month Window (${daily[0].date} to ${daily[daily.length - 1].date})`;
  } else if (currentTimeframe === "1Y") {
    daily = daily.slice(-252);
    windowTitle = `1-Year Window (${daily[0].date} to ${daily[daily.length - 1].date})`;
  } else if (currentTimeframe === "5Y") {
    daily = daily.filter(r => r.date >= "2021-01-01");
    windowTitle = `5-Year Window (2021 to 2026 • ${daily.length} Sessions)`;
  } else if (currentTimeframe === "2022") {
    daily = daily.filter(r => r.date >= "2022-01-01" && r.date <= "2022-12-31");
    windowTitle = `2022 Tech Bear Market (251 Sessions)`;
  } else if (currentTimeframe === "2020") {
    daily = daily.filter(r => r.date >= "2020-01-01" && r.date <= "2020-12-31");
    windowTitle = `2020 COVID Flash Crash (253 Sessions)`;
  } else if (currentTimeframe === "CUSTOM") {
    const start = customStartDate || "2010-02-11";
    const end = customEndDate || "2026-03-30";
    daily = daily.filter(r => r.date >= start && r.date <= end);
    windowTitle = `Custom Window: ${start} to ${end} (${daily.length} Sessions)`;
  }

  // Filter trades to current window dates
  if (daily.length > 0) {
    const minD = daily[0].date;
    const maxD = daily[daily.length - 1].date;
    trades = trades.filter(t => {
      const d = t.timestamp ? t.timestamp.substring(0, 10) : "";
      return d >= minD && d <= maxD;
    });
  }

  const elWindowText = document.getElementById("qmWindowText");
  if (elWindowText) elWindowText.textContent = `Window: ${windowTitle}`;

  if (daily.length < 2) return;

  // 1. Daily returns
  const vals = daily.map(r => r.total_value);
  const returns = [];
  const negReturns = [];
  const rfDaily = Math.pow(1 + 0.045, 1 / 252) - 1;
  const excessReturns = [];

  for (let i = 1; i < vals.length; i++) {
    const r = (vals[i] - vals[i - 1]) / vals[i - 1];
    returns.push(r);
    const ex = r - rfDaily;
    excessReturns.push(ex);
    if (r < 0) negReturns.push(r);
  }

  // Mean & Standard Deviations
  const meanExcess = excessReturns.reduce((a, b) => a + b, 0) / excessReturns.length;
  const meanReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
  
  const variance = returns.reduce((a, b) => a + Math.pow(b - meanReturn, 2), 0) / returns.length;
  const stdDev = Math.sqrt(variance);

  const meanNeg = negReturns.length > 0 ? (negReturns.reduce((a, b) => a + b, 0) / negReturns.length) : 0;
  const negVariance = negReturns.reduce((a, b) => a + Math.pow(b - meanNeg, 2), 0) / (negReturns.length || 1);
  const downsideStdDev = Math.sqrt(negVariance);

  // Annualized Sharpe & Sortino
  const annSharpe = stdDev > 0 ? (Math.sqrt(252) * meanExcess / stdDev) : 0;
  const annSortino = downsideStdDev > 0 ? (Math.sqrt(252) * meanExcess / downsideStdDev) : 0;

  // 16Y CAGR
  const nYears = vals.length / 252;
  const cagr = Math.pow(vals[vals.length - 1] / vals[0], 1 / nYears) - 1;

  // Max Drawdown & Calmar
  let hwm = vals[0];
  let maxDd = 0;
  let peakDate = new Date(daily[0].date);
  let maxDurationDays = 0;

  for (let i = 0; i < daily.length; i++) {
    const v = daily[i].total_value;
    const curDate = new Date(daily[i].date);
    if (v >= hwm) {
      const dur = Math.round((curDate - peakDate) / (1000 * 60 * 60 * 24));
      if (dur > maxDurationDays) maxDurationDays = dur;
      hwm = v;
      peakDate = curDate;
    } else {
      const dd = (v - hwm) / hwm;
      if (dd < maxDd) maxDd = dd;
    }
  }

  const finalDur = Math.round((new Date(daily[daily.length - 1].date) - peakDate) / (1000 * 60 * 60 * 24));
  if (finalDur > maxDurationDays) maxDurationDays = finalDur;

  const calmar = Math.abs(maxDd) > 0 ? (cagr / Math.abs(maxDd)) : 0;

  // Trade Cycles metrics
  const cycles = computeTradeCycles(trades);
  const wins = cycles.filter(c => c.pnlDollar > 0);
  const losses = cycles.filter(c => c.pnlDollar <= 0);
  const winRate = cycles.length > 0 ? (wins.length / cycles.length * 100) : 0;

  const grossProfit = wins.reduce((acc, c) => acc + c.pnlDollar, 0);
  const grossLoss = Math.abs(losses.reduce((acc, c) => acc + c.pnlDollar, 0));
  const profitFactor = grossLoss > 0 ? (grossProfit / grossLoss) : (grossProfit > 0 ? 99.9 : 0);

  const avgWinPct = wins.length > 0 ? (wins.reduce((acc, c) => acc + c.pnlPct, 0) / wins.length) : 0;
  const avgLossPct = losses.length > 0 ? (losses.reduce((acc, c) => acc + c.pnlPct, 0) / losses.length) : 0;
  const payoffRatio = Math.abs(avgLossPct) > 0 ? (avgWinPct / Math.abs(avgLossPct)) : 0;

  // Update DOM Elements
  const elSharpe = document.getElementById("qmSharpe");
  if (elSharpe) elSharpe.textContent = annSharpe.toFixed(2);

  const elSortino = document.getElementById("qmSortino");
  if (elSortino) elSortino.textContent = annSortino.toFixed(2);

  const elCalmar = document.getElementById("qmCalmar");
  if (elCalmar) elCalmar.textContent = calmar.toFixed(2);

  const elCagr = document.getElementById("qmCagr");
  if (elCagr) elCagr.textContent = `${cagr >= 0 ? '+' : ''}${(cagr * 100).toFixed(1)}%`;

  const elPF = document.getElementById("qmProfitFactor");
  if (elPF) elPF.textContent = `${profitFactor.toFixed(2)}×`;

  const elPFSub = document.getElementById("qmProfitFactorSub");
  if (elPFSub) elPFSub.textContent = `$${(grossProfit / 1000).toFixed(0)}k Win / $${(grossLoss / 1000).toFixed(0)}k Loss`;

  const elWinRate = document.getElementById("qmWinRate");
  if (elWinRate) elWinRate.textContent = `${winRate.toFixed(1)}%`;

  const elWinCount = document.getElementById("qmWinLossCount");
  if (elWinCount) elWinCount.textContent = `${wins.length} Wins / ${losses.length} Losses`;

  const elPayoff = document.getElementById("qmPayoffRatio");
  if (elPayoff) elPayoff.textContent = `${payoffRatio.toFixed(2)}×`;

  const elPayoffSub = document.getElementById("qmPayoffSub");
  if (elPayoffSub) elPayoffSub.textContent = `+${avgWinPct.toFixed(1)}% / ${avgLossPct.toFixed(1)}%`;

  const elMaxDur = document.getElementById("qmMaxDdDuration");
  if (elMaxDur) elMaxDur.textContent = `${maxDurationDays} days`;
}

/* ==========================================================================
   2. FORWARD TRIGGER RADAR RENDERER
   ========================================================================== */
function renderTriggerRadar(data) {
  const modelObj = (data.models && data.models[currentModel]) ? data.models[currentModel] : data;
  const p = modelObj.portfolio || data.portfolio;
  const stats = modelObj.stats || data.stats;
  const daily = modelObj.daily_summary || data.daily_summary || [];

  if (!daily || daily.length === 0) return;
  const latest = daily[daily.length - 1];

  const curNdx = latest.ndx_price || stats.ndx_price || 0;
  const curSma50 = latest.sma50 || stats.sma50 || 0;
  const curAtr = stats.atr || 280.0;
  const curRsi = latest.rsi || stats.rsi || 50.0;

  // Determine Stop / Exit Threshold for active model
  let exitThreshold = 0;
  let conditionText = "";

  if (currentModel === "symmetric_atr") {
    exitThreshold = curSma50 - (1.0 * curAtr);
    conditionText = `Requires NDX close below SMA50 - 1.0× ATR (${exitThreshold.toFixed(1)})`;
  } else {
    exitThreshold = curSma50;
    conditionText = `Requires NDX close below 50-day SMA (${exitThreshold.toFixed(1)})`;
  }

  const distPts = curNdx - exitThreshold;
  const distPct = exitThreshold > 0 ? (distPts / exitThreshold) * 100 : 0;

  const elExitPrice = document.getElementById("radarExitPrice");
  if (elExitPrice) elExitPrice.textContent = `NDX ${exitThreshold.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`;

  const elExitDist = document.getElementById("radarExitDistance");
  if (elExitDist) {
    elExitDist.textContent = `${distPts >= 0 ? '+' : ''}${distPts.toFixed(1)} pts (${distPct >= 0 ? '+' : ''}${distPct.toFixed(2)}%)`;
    if (distPct > 2.0) {
      elExitDist.className = "radar-cushion font-mono text-emerald";
    } else if (distPct > 0.8) {
      elExitDist.className = "radar-cushion font-mono text-amber";
    } else {
      elExitDist.className = "radar-cushion font-mono text-rose";
    }
  }

  const elCondition = document.getElementById("radarExitCondition");
  if (elCondition) elCondition.textContent = conditionText;

  // RSI Overbought Headroom
  const rsiHeadroom = 75.0 - curRsi;
  const elRsiHeadroom = document.getElementById("radarRsiHeadroom");
  if (elRsiHeadroom) {
    if (rsiHeadroom <= 0) {
      elRsiHeadroom.textContent = "TRIM ACTIVE (Overbought triggered)";
      elRsiHeadroom.className = "radar-cushion text-rose font-mono";
    } else {
      elRsiHeadroom.textContent = `${rsiHeadroom.toFixed(1)} pts remaining before trim`;
      elRsiHeadroom.className = "radar-cushion text-pink font-mono";
    }
  }

  // Regime Streak calculation (consecutive trading sessions in current position)
  let streak = 0;
  const targetPos = p.position;
  for (let i = daily.length - 1; i >= 0; i--) {
    if (daily[i].position === targetPos) {
      streak++;
    } else {
      break;
    }
  }
  const elStreak = document.getElementById("radarRegimeStreak");
  if (elStreak) elStreak.textContent = `${streak} sessions`;

  // All-Time High Proximity
  let maxNdx = 0;
  for (let i = 0; i < daily.length; i++) {
    if (daily[i].ndx_price > maxNdx) maxNdx = daily[i].ndx_price;
  }
  const athDiffPct = maxNdx > 0 ? ((curNdx / maxNdx) - 1) * 100 : 0;
  const elAth = document.getElementById("radarAthProximity");
  if (elAth) {
    elAth.textContent = `${athDiffPct >= 0 ? 'AT ATH' : `${athDiffPct.toFixed(2)}% vs ATH`}`;
    elAth.className = athDiffPct >= -1.0 ? "radar-mini-val font-mono text-emerald" : "radar-mini-val font-mono text-cyan";
  }
}

/* ==========================================================================
   3. ANNUAL PERFORMANCE & CRISIS ALPHA MATRIX
   ========================================================================== */
function renderAnnualMatrix(data) {
  const tableBody = document.getElementById("annualMatrixBody");
  if (!tableBody || !data.models) return;

  const activeModelObj = data.models[currentModel] || data;
  const altModelKey = currentModel === "symmetric_atr" ? "original_agile" : "symmetric_atr";
  const altModelObj = data.models[altModelKey] || null;

  const dailyActive = activeModelObj.daily_summary || [];
  const dailyAlt = (altModelObj && altModelObj.daily_summary) ? altModelObj.daily_summary : [];

  if (dailyActive.length === 0) return;

  // Group by calendar year
  const yearsMap = {};
  dailyActive.forEach(r => {
    const yr = r.date.substring(0, 4);
    if (!yearsMap[yr]) yearsMap[yr] = { active: [], alt: [] };
    yearsMap[yr].active.push(r);
  });

  dailyAlt.forEach(r => {
    const yr = r.date.substring(0, 4);
    if (yearsMap[yr]) yearsMap[yr].alt.push(r);
  });

  const sortedYears = Object.keys(yearsMap).sort().reverse();
  const crisisYears = ["2022", "2020", "2018", "2015", "2011"];

  const displayYears = currentMatrixView === "crisis" 
    ? sortedYears.filter(y => crisisYears.includes(y))
    : sortedYears;

  let rowsHtml = "";

  displayYears.forEach(yr => {
    const activeRecords = yearsMap[yr].active;
    const altRecords = yearsMap[yr].alt;

    if (!activeRecords || activeRecords.length < 2) return;

    // Measure from prior year-end close (standard calendar-year accounting)
    const prevYr = (parseInt(yr, 10) - 1).toString();
    const prevActive = yearsMap[prevYr] ? yearsMap[prevYr].active : null;
    const prevAlt = yearsMap[prevYr] ? yearsMap[prevYr].alt : null;

    // Active Return
    const aStart = (prevActive && prevActive.length > 0) ? prevActive[prevActive.length - 1].total_value : activeRecords[0].total_value;
    const aEnd = activeRecords[activeRecords.length - 1].total_value;
    const aRet = ((aEnd / aStart) - 1) * 100;

    // Alt Return
    let altRet = 0;
    if (altRecords && altRecords.length >= 2) {
      const altStart = (prevAlt && prevAlt.length > 0) ? prevAlt[prevAlt.length - 1].total_value : altRecords[0].total_value;
      const altEnd = altRecords[altRecords.length - 1].total_value;
      altRet = ((altEnd / altStart) - 1) * 100;
    }

    // NDX Return
    const ndxStart = (prevActive && prevActive.length > 0) ? prevActive[prevActive.length - 1].ndx_price : activeRecords[0].ndx_price;
    const ndxEnd = activeRecords[activeRecords.length - 1].ndx_price;
    const ndxRet = ((ndxEnd / ndxStart) - 1) * 100;

    // TQQQ Return
    const tqqqStartRatio = (prevActive && prevActive.length > 0) 
      ? (1 + (prevActive[prevActive.length - 1].tqqq_buyhold_pnl_pct || 0) / 100) 
      : (1 + (activeRecords[0].tqqq_buyhold_pnl_pct || 0) / 100);
    const tqqqEndRatio = 1 + (activeRecords[activeRecords.length - 1].tqqq_buyhold_pnl_pct || 0) / 100;
    const tqqqRet = ((tqqqEndRatio / tqqqStartRatio) - 1) * 100;

    // Alpha vs NDX
    const alpha = aRet - ndxRet;

    // Max Drawdown during this year
    let yrHwm = aStart;
    let yrMaxDd = 0;
    activeRecords.forEach(r => {
      if (r.total_value > yrHwm) yrHwm = r.total_value;
      const dd = (r.total_value - yrHwm) / yrHwm * 100;
      if (dd < yrMaxDd) yrMaxDd = dd;
    });

    // Outcome Tag
    let outcomeHtml = "";
    if (yr === "2022") {
      outcomeHtml = `<span class="matrix-badge-defense"><i class="fa-solid fa-shield"></i> CRISIS ALPHA</span>`;
    } else if (yr === "2020") {
      outcomeHtml = `<span class="matrix-badge-win"><i class="fa-solid fa-bolt"></i> COVID REBOUND</span>`;
    } else if (yr === "2018") {
      outcomeHtml = `<span class="matrix-badge-defense"><i class="fa-solid fa-shield-halved"></i> BEAR DEFENSE</span>`;
    } else if (aRet >= ndxRet && aRet > 0) {
      outcomeHtml = `<span class="matrix-badge-win"><i class="fa-solid fa-trophy"></i> OUTPERFORM</span>`;
    } else if (aRet > 0) {
      outcomeHtml = `<span class="text-emerald font-mono">POSITIVE</span>`;
    } else {
      outcomeHtml = `<span class="text-rose font-mono">DRAWDOWN</span>`;
    }

    let alphaBadgeClass = "alpha-pos";
    if (alpha >= 50) alphaBadgeClass = "alpha-huge-pos";
    else if (alpha < 0) alphaBadgeClass = "alpha-neg";

    rowsHtml += `
      <tr>
        <td><strong>${yr}</strong></td>
        <td class="${aRet >= 0 ? 'cell-ret-pos' : 'cell-ret-neg'}">${aRet >= 0 ? '+' : ''}${aRet.toFixed(1)}%</td>
        <td class="${altRet >= 0 ? 'cell-ret-pos' : 'cell-ret-neg'}">${altRet >= 0 ? '+' : ''}${altRet.toFixed(1)}%</td>
        <td class="${ndxRet >= 0 ? 'text-muted' : 'text-rose'}">${ndxRet >= 0 ? '+' : ''}${ndxRet.toFixed(1)}%</td>
        <td class="${tqqqRet >= 0 ? 'text-amber' : 'text-rose'}">${tqqqRet >= 0 ? '+' : ''}${tqqqRet.toFixed(1)}%</td>
        <td><span class="alpha-badge ${alphaBadgeClass}">${alpha >= 0 ? '+' : ''}${alpha.toFixed(1)}%</span></td>
        <td class="text-rose">${yrMaxDd.toFixed(1)}%</td>
        <td>${outcomeHtml}</td>
      </tr>
    `;
  });

  tableBody.innerHTML = rowsHtml;

  // Update Crisis Highlight Cards for active model
  if (yearsMap["2022"]) {
    const a22 = yearsMap["2022"].active;
    const prev21 = yearsMap["2021"] ? yearsMap["2021"].active : null;
    const base22 = (prev21 && prev21.length > 0) ? prev21[prev21.length - 1].total_value : a22[0].total_value;
    const ret22 = ((a22[a22.length - 1].total_value / base22) - 1) * 100;
    const el22 = document.getElementById("crisis2022Val");
    if (el22) el22.textContent = `${ret22 >= 0 ? '+' : ''}${ret22.toFixed(1)}%`;
    const pill22 = document.getElementById("crisis2022Pill");
    if (pill22) pill22.textContent = `+${(ret22 - (-79.1)).toFixed(1)}% vs TQQQ`;
  }

  if (yearsMap["2020"]) {
    const a20 = yearsMap["2020"].active;
    const prev19 = yearsMap["2019"] ? yearsMap["2019"].active : null;
    const base20 = (prev19 && prev19.length > 0) ? prev19[prev19.length - 1].total_value : a20[0].total_value;
    const ret20 = ((a20[a20.length - 1].total_value / base20) - 1) * 100;
    const el20 = document.getElementById("crisis2020Val");
    if (el20) el20.textContent = `${ret20 >= 0 ? '+' : ''}${ret20.toFixed(1)}%`;
    const pill20 = document.getElementById("crisis2020Pill");
    if (pill20) pill20.textContent = `+${(ret20 - 47.6).toFixed(1)}% Alpha vs NDX`;
  }

  if (yearsMap["2018"]) {
    const a18 = yearsMap["2018"].active;
    const prev17 = yearsMap["2017"] ? yearsMap["2017"].active : null;
    const base18 = (prev17 && prev17.length > 0) ? prev17[prev17.length - 1].total_value : a18[0].total_value;
    const ret18 = ((a18[a18.length - 1].total_value / base18) - 1) * 100;
    const el18 = document.getElementById("crisis2018Val");
    if (el18) el18.textContent = `${ret18 >= 0 ? '+' : ''}${ret18.toFixed(1)}%`;
    const pill18 = document.getElementById("crisis2018Pill");
    if (pill18) pill18.textContent = `+${(ret18 - (-19.8)).toFixed(1)}% vs TQQQ`;
  }
}

/* ==========================================================================
   4. SIDEBAR TELEMETRY GAUGES
   ========================================================================== */
function renderSidebarTelemetry(data, scaleFactor) {
  const modelObj = (data.models && data.models[currentModel]) ? data.models[currentModel] : data;
  const p = modelObj.portfolio || data.portfolio;
  const stats = modelObj.stats || data.stats;
  const tradesList = modelObj.trades || data.trades || [];
  const daily = modelObj.daily_summary || data.daily_summary || [];

  // Gauge 1: Exit Threshold Distance
  const telSma50Val = document.getElementById("telSma50Val");
  const telSma50Fill = document.getElementById("telSma50Fill");
  if (telSma50Val && stats.dist_sma50_pts !== undefined) {
    telSma50Val.textContent = `${stats.dist_sma50_pts >= 0 ? '+' : ''}${stats.dist_sma50_pts.toFixed(1)} pts (${stats.dist_sma50_pct >= 0 ? '+' : ''}${stats.dist_sma50_pct.toFixed(2)}%)`;
    const fillPct = Math.min(100, Math.max(0, 50 + stats.dist_sma50_pct * 5));
    if (telSma50Fill) telSma50Fill.style.width = `${fillPct}%`;
  }

  // Gauge 2: RSI Heat Level
  const telRsiVal = document.getElementById("telRsiVal");
  const telRsiFill = document.getElementById("telRsiFill");
  if (telRsiVal && stats.rsi !== undefined) {
    telRsiVal.textContent = `${stats.rsi.toFixed(1)} / 75`;
    const fillRsi = Math.min(100, Math.max(0, (stats.rsi / 100) * 100));
    if (telRsiFill) telRsiFill.style.width = `${fillRsi}%`;
  }

  // Gauge 3: Asset Mix
  const telAllocVal = document.getElementById("telAllocVal");
  const allocTqqq = document.getElementById("allocTqqq");
  const allocCash = document.getElementById("allocCash");
  const allocTqqqPct = document.getElementById("allocTqqqPct");
  const allocCashPct = document.getElementById("allocCashPct");

  const tqqqPctVal = Math.round((p.allocation_pct || 0) * 100);
  const cashPctVal = 100 - tqqqPctVal;

  if (telAllocVal) telAllocVal.textContent = `${tqqqPctVal}% TQQQ / ${cashPctVal}% Cash`;
  if (allocTqqq) allocTqqq.style.width = `${tqqqPctVal}%`;
  if (allocCash) allocCash.style.width = `${cashPctVal}%`;
  if (allocTqqqPct) allocTqqqPct.textContent = `${tqqqPctVal}%`;
  if (allocCashPct) allocCashPct.textContent = `${cashPctVal}%`;

  // Quick stats
  const statTrades = document.getElementById("statTotalTrades");
  if (statTrades) statTrades.textContent = (stats && stats.total_trades) || tradesList.length || 0;
  const statDays = document.getElementById("statDaysTracked");
  if (statDays) statDays.textContent = `${(stats && stats.trading_days_tracked) || daily.length} days`;
  const statDD = document.getElementById("statMaxDD");
  if (statDD) statDD.textContent = `${((stats && stats.max_drawdown_pct) !== undefined ? stats.max_drawdown_pct : 0).toFixed(2)}%`;
  const statHWM = document.getElementById("statHWM");
  if (statHWM) statHWM.textContent = formatCurrency(((stats && stats.high_water_mark) || p.total_value || 10000) * scaleFactor);
}

/* ==========================================================================
   5. CHART RENDERING (EQUITY, TECHNICALS, RSI, DRAWDOWN)
   ========================================================================== */
function renderChart() {
  if (!cachedData) return;

  const ctx = document.getElementById("mainChart").getContext("2d");
  
  const activeModelObj = (cachedData.models && cachedData.models[currentModel]) ? cachedData.models[currentModel] : cachedData;
  const otherModelKey = currentModel === "symmetric_atr" ? "original_agile" : "symmetric_atr";
  const otherModelObj = (cachedData.models && cachedData.models[otherModelKey]) ? cachedData.models[otherModelKey] : null;

  let records = activeModelObj.daily_summary ? [...activeModelObj.daily_summary] : [...(cachedData.daily_summary || [])];
  let otherRecords = (otherModelObj && otherModelObj.daily_summary) ? [...otherModelObj.daily_summary] : null;
  if (!records || records.length === 0) return;

  // Apply Timeframe & Era Filters
  if (currentTimeframe === "1M") {
    records = records.slice(-22);
    if (otherRecords) otherRecords = otherRecords.slice(-22);
  } else if (currentTimeframe === "6M") {
    records = records.slice(-126);
    if (otherRecords) otherRecords = otherRecords.slice(-126);
  } else if (currentTimeframe === "1Y") {
    records = records.slice(-252);
    if (otherRecords) otherRecords = otherRecords.slice(-252);
  } else if (currentTimeframe === "5Y") {
    records = records.filter(r => r.date >= "2021-01-01");
    if (otherRecords) otherRecords = otherRecords.filter(r => r.date >= "2021-01-01");
  } else if (currentTimeframe === "2022") {
    records = records.filter(r => r.date >= "2022-01-01" && r.date <= "2022-12-31");
    if (otherRecords) otherRecords = otherRecords.filter(r => r.date >= "2022-01-01" && r.date <= "2022-12-31");
  } else if (currentTimeframe === "2020") {
    records = records.filter(r => r.date >= "2020-01-01" && r.date <= "2020-12-31");
    if (otherRecords) otherRecords = otherRecords.filter(r => r.date >= "2020-01-01" && r.date <= "2020-12-31");
  } else if (currentTimeframe === "CUSTOM") {
    const start = customStartDate || "2010-02-11";
    const end = customEndDate || "2026-03-30";
    records = records.filter(r => r.date >= start && r.date <= end);
    if (otherRecords) otherRecords = otherRecords.filter(r => r.date >= start && r.date <= end);
  }

  // Handle Sandbox Custom Model overlay data if active
  let plotSbRecords = null;
  if (sandboxCustomModelResult && sandboxCustomModelResult.records) {
    let sbRecs = [...sandboxCustomModelResult.records];
    if (currentTimeframe === "1M") sbRecs = sbRecs.slice(-22);
    else if (currentTimeframe === "6M") sbRecs = sbRecs.slice(-126);
    else if (currentTimeframe === "1Y") sbRecs = sbRecs.slice(-252);
    else if (currentTimeframe === "5Y") sbRecs = sbRecs.filter(r => r.date >= "2021-01-01");
    else if (currentTimeframe === "2022") sbRecs = sbRecs.filter(r => r.date >= "2022-01-01" && r.date <= "2022-12-31");
    else if (currentTimeframe === "2020") sbRecs = sbRecs.filter(r => r.date >= "2020-01-01" && r.date <= "2020-12-31");
    else if (currentTimeframe === "CUSTOM") {
      const start = customStartDate || "2010-02-11";
      const end = customEndDate || "2026-03-30";
      sbRecs = sbRecs.filter(r => r.date >= start && r.date <= end);
    }
    plotSbRecords = sbRecs;
  }

  // Smooth dataset sampling for responsive 60fps canvas performance
  let plotRecords = records;
  let plotOtherRecords = otherRecords;
  if (plotRecords.length > 500) {
    const step = Math.ceil(plotRecords.length / 400);
    const sampled = [];
    const sampledOther = [];
    const sampledSb = plotSbRecords ? [] : null;
    for (let i = 0; i < plotRecords.length; i += step) {
      sampled.push(plotRecords[i]);
      if (plotOtherRecords && plotOtherRecords[i]) sampledOther.push(plotOtherRecords[i]);
      if (sampledSb && plotSbRecords[i]) sampledSb.push(plotSbRecords[i]);
    }
    if (sampled[sampled.length - 1] !== plotRecords[plotRecords.length - 1]) {
      sampled.push(plotRecords[plotRecords.length - 1]);
      if (plotOtherRecords && plotOtherRecords.length > 0) sampledOther.push(plotOtherRecords[plotOtherRecords.length - 1]);
      if (sampledSb && plotSbRecords && plotSbRecords.length > 0) sampledSb.push(plotSbRecords[plotSbRecords.length - 1]);
    }
    plotRecords = sampled;
    if (plotOtherRecords && plotOtherRecords.length > 0) plotOtherRecords = sampledOther;
    if (sampledSb && sampledSb.length > 0) plotSbRecords = sampledSb;
  }

  const labels = plotRecords.map(r => r.date);
  const legendBox = document.getElementById("chartLegend");

  if (chartInstance) {
    chartInstance.destroy();
  }

  const activeName = currentModel === "symmetric_atr" ? "Symmetric 1.0× ATR" : "Original Agile (1% Buffer)";
  const otherName = currentModel === "symmetric_atr" ? "Original Agile (1% Buffer)" : "Symmetric 1.0× ATR";
  const activeColor = currentModel === "symmetric_atr" ? "#00F2FE" : "#10B981";
  const otherColor = currentModel === "symmetric_atr" ? "#10B981" : "#00F2FE";

  if (currentTab === "equity") {
    // --- TAB 1: EQUITY VS BENCHMARKS (REBASED TO TIMEFRAME START) ---
    const r0 = plotRecords[0];
    const stratStartVal = Math.max(0.0001, r0.total_value);
    const ndxStartRatio = Math.max(0.0001, 1 + (r0.ndx_buyhold_pnl_pct || 0) / 100);
    const tqqqStartRatio = Math.max(0.0001, 1 + (r0.tqqq_buyhold_pnl_pct || 0) / 100);

    const activeEquityData = plotRecords.map(r => simulatedCapital * (r.total_value / stratStartVal));
    const baseLine = plotRecords.map(() => simulatedCapital);
    const ndxNorm = plotRecords.map(r => simulatedCapital * ((1 + (r.ndx_buyhold_pnl_pct || 0) / 100) / ndxStartRatio));
    const tqqqNorm = plotRecords.map(r => simulatedCapital * ((1 + (r.tqqq_buyhold_pnl_pct || 0) / 100) / tqqqStartRatio));

    const activeEndVal = activeEquityData[activeEquityData.length - 1];
    const ndxEndVal = ndxNorm[ndxNorm.length - 1];
    const tqqqEndVal = tqqqNorm[tqqqNorm.length - 1];

    const activeRet = ((activeEndVal / simulatedCapital) - 1) * 100;
    const ndxRet = ((ndxEndVal / simulatedCapital) - 1) * 100;
    const tqqqRet = ((tqqqEndVal / simulatedCapital) - 1) * 100;

    const gradActive = ctx.createLinearGradient(0, 0, 0, 350);
    if (currentModel === "symmetric_atr") {
      gradActive.addColorStop(0, "rgba(0, 242, 254, 0.28)");
      gradActive.addColorStop(1, "rgba(0, 242, 254, 0.0)");
    } else {
      gradActive.addColorStop(0, "rgba(16, 185, 129, 0.28)");
      gradActive.addColorStop(1, "rgba(16, 185, 129, 0.0)");
    }

    const datasets = [
      {
        label: `${activeName} (Active)`,
        data: activeEquityData,
        borderColor: activeColor,
        borderWidth: 2.5,
        backgroundColor: gradActive,
        fill: true,
        tension: 0.2,
        pointRadius: plotRecords.length > 60 ? 0 : 3,
        pointHoverRadius: 6,
      }
    ];

    let otherLegendHtml = "";
    if (overlayBothModels && plotOtherRecords && plotOtherRecords.length > 0) {
      const otherR0 = plotOtherRecords[0];
      const otherStartVal = Math.max(0.0001, otherR0.total_value);
      const otherEquityData = plotOtherRecords.map(r => simulatedCapital * (r.total_value / otherStartVal));
      const otherEndVal = otherEquityData[otherEquityData.length - 1];
      const otherRet = ((otherEndVal / simulatedCapital) - 1) * 100;

      datasets.push({
        label: otherName,
        data: otherEquityData,
        borderColor: otherColor,
        borderWidth: 2.0,
        borderDash: [4, 4],
        fill: false,
        tension: 0.2,
        pointRadius: plotOtherRecords.length > 60 ? 0 : 2,
        pointHoverRadius: 5,
      });

      otherLegendHtml = `<div class="legend-item"><span class="legend-color-box" style="background:${otherColor}; border: 1px dashed white;"></span> ${otherName}: <strong>${formatCurrency(otherEndVal)}</strong> (${otherRet >= 0 ? '+' : ''}${otherRet.toFixed(2)}%)</div>`;
    }

    let sbLegendHtml = "";
    if (plotSbRecords && plotSbRecords.length > 0) {
      const sbR0 = plotSbRecords[0];
      const sbStartVal = Math.max(0.0001, sbR0.total_value);
      const sbEquityData = plotSbRecords.map(r => simulatedCapital * (r.total_value / sbStartVal));
      const sbEndVal = sbEquityData[sbEquityData.length - 1];
      const sbRet = ((sbEndVal / simulatedCapital) - 1) * 100;

      datasets.push({
        label: `${sandboxCustomModelResult.name} (Sandbox)`,
        data: sbEquityData,
        borderColor: "#F59E0B",
        borderWidth: 2.2,
        borderDash: [5, 3],
        fill: false,
        tension: 0.2,
        pointRadius: plotSbRecords.length > 60 ? 0 : 2,
        pointHoverRadius: 5,
      });

      sbLegendHtml = `<div class="legend-item"><span class="legend-color-box" style="background:#F59E0B; border: 1px dashed white;"></span> ${sandboxCustomModelResult.name}: <strong>${formatCurrency(sbEndVal)}</strong> (${sbRet >= 0 ? '+' : ''}${sbRet.toFixed(2)}%) <a href="#" id="btnClearSandboxOverlay" style="color: #F43F5E; margin-left: 6px; text-decoration: underline; font-size: 11px;">[Remove]</a></div>`;
    }

    datasets.push(
      {
        label: `Baseline ($${(simulatedCapital / 1000).toFixed(0)}k)`,
        data: baseLine,
        borderColor: "rgba(255, 255, 255, 0.3)",
        borderWidth: 1.5,
        borderDash: [5, 5],
        fill: false,
        pointRadius: 0,
      },
      {
        label: "NDX Buy & Hold",
        data: ndxNorm,
        borderColor: "#A855F7",
        borderWidth: 1.5,
        fill: false,
        tension: 0.2,
        pointRadius: 0,
      },
      {
        label: "TQQQ Buy & Hold",
        data: tqqqNorm,
        borderColor: "#F59E0B",
        borderWidth: 1.5,
        fill: false,
        tension: 0.2,
        pointRadius: 0,
      }
    );

    chartInstance = new Chart(ctx, {
      type: "line",
      data: { labels: labels, datasets: datasets },
      options: getCommonChartOptions("$")
    });

    legendBox.innerHTML = `
      <div class="legend-item"><span class="legend-color-box" style="background:${activeColor};"></span> ${activeName} (Active): <strong>${formatCurrency(activeEndVal)}</strong> (${activeRet >= 0 ? '+' : ''}${activeRet.toFixed(2)}%)</div>
      ${otherLegendHtml}
      ${sbLegendHtml}
      <div class="legend-item"><span class="legend-color-box" style="background:#A855F7;"></span> NDX: <strong>${formatCurrency(ndxEndVal)}</strong> (${ndxRet >= 0 ? '+' : ''}${ndxRet.toFixed(2)}%)</div>
      <div class="legend-item"><span class="legend-color-box" style="background:#F59E0B;"></span> TQQQ: <strong>${formatCurrency(tqqqEndVal)}</strong> (${tqqqRet >= 0 ? '+' : ''}${tqqqRet.toFixed(2)}%)</div>
      <div class="legend-item"><span class="legend-color-box" style="background:rgba(255,255,255,0.4); border: 1px dashed white;"></span> Baseline: <strong>${formatCurrency(simulatedCapital)}</strong></div>
    `;

  } else if (currentTab === "drawdown") {
    // --- TAB 4: DRAWDOWN & UNDERWATER PROFILE ---
    // Compute peak-to-trough decline from HWM for active model
    let hwmActive = plotRecords[0].total_value;
    const activeDdData = plotRecords.map(r => {
      if (r.total_value > hwmActive) hwmActive = r.total_value;
      return ((r.total_value - hwmActive) / hwmActive) * 100;
    });

    // NDX Drawdown
    let hwmNdx = plotRecords[0].ndx_price;
    const ndxDdData = plotRecords.map(r => {
      if (r.ndx_price > hwmNdx) hwmNdx = r.ndx_price;
      return ((r.ndx_price - hwmNdx) / hwmNdx) * 100;
    });

    // TQQQ Drawdown
    let hwmTqqq = 1 + (plotRecords[0].tqqq_buyhold_pnl_pct || 0) / 100;
    const tqqqDdData = plotRecords.map(r => {
      const norm = 1 + (r.tqqq_buyhold_pnl_pct || 0) / 100;
      if (norm > hwmTqqq) hwmTqqq = norm;
      return ((norm - hwmTqqq) / hwmTqqq) * 100;
    });

    const gradDd = ctx.createLinearGradient(0, 0, 0, 350);
    gradDd.addColorStop(0, "rgba(0, 242, 254, 0.0)");
    gradDd.addColorStop(1, "rgba(0, 242, 254, 0.2)");

    const datasets = [
      {
        label: `${activeName} (Active)`,
        data: activeDdData,
        borderColor: activeColor,
        borderWidth: 2.2,
        backgroundColor: gradDd,
        fill: true,
        tension: 0.15,
        pointRadius: 0,
      }
    ];

    let otherDdLegend = "";
    if (overlayBothModels && plotOtherRecords && plotOtherRecords.length > 0) {
      let hwmOther = plotOtherRecords[0].total_value;
      const otherDdData = plotOtherRecords.map(r => {
        if (r.total_value > hwmOther) hwmOther = r.total_value;
        return ((r.total_value - hwmOther) / hwmOther) * 100;
      });

      datasets.push({
        label: otherName,
        data: otherDdData,
        borderColor: otherColor,
        borderWidth: 1.8,
        borderDash: [4, 4],
        fill: false,
        tension: 0.15,
        pointRadius: 0,
      });

      const otherMinDd = Math.min(...otherDdData);
      otherDdLegend = `<div class="legend-item"><span class="legend-color-box" style="background:${otherColor}; border: 1px dashed white;"></span> ${otherName}: Max DD <strong>${otherMinDd.toFixed(2)}%</strong></div>`;
    }

    let sbDdLegend = "";
    if (plotSbRecords && plotSbRecords.length > 0) {
      let hwmSb = plotSbRecords[0].total_value;
      const sbDdData = plotSbRecords.map(r => {
        if (r.total_value > hwmSb) hwmSb = r.total_value;
        return ((r.total_value - hwmSb) / hwmSb) * 100;
      });

      datasets.push({
        label: `${sandboxCustomModelResult.name} (Sandbox)`,
        data: sbDdData,
        borderColor: "#F59E0B",
        borderWidth: 2.0,
        borderDash: [5, 3],
        fill: false,
        tension: 0.15,
        pointRadius: 0
      });

      const sbMinDd = Math.min(...sbDdData);
      sbDdLegend = `<div class="legend-item"><span class="legend-color-box" style="background:#F59E0B; border: 1px dashed white;"></span> ${sandboxCustomModelResult.name}: Max DD <strong>${sbMinDd.toFixed(2)}%</strong></div>`;
    }

    datasets.push(
      {
        label: "NDX Drawdown",
        data: ndxDdData,
        borderColor: "#A855F7",
        borderWidth: 1.5,
        fill: false,
        tension: 0.15,
        pointRadius: 0,
      },
      {
        label: "TQQQ Drawdown (Unhedged)",
        data: tqqqDdData,
        borderColor: "#F43F5E",
        borderWidth: 1.8,
        fill: false,
        tension: 0.15,
        pointRadius: 0,
      }
    );

    const activeMinDd = Math.min(...activeDdData);
    const ndxMinDd = Math.min(...ndxDdData);
    const tqqqMinDd = Math.min(...tqqqDdData);

    chartInstance = new Chart(ctx, {
      type: "line",
      data: { labels: labels, datasets: datasets },
      options: {
        ...getCommonChartOptions("%"),
        scales: {
          ...getCommonChartOptions("%").scales,
          y: {
            min: -100,
            max: 0,
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: {
              color: "#94A3B8",
              font: { family: "'JetBrains Mono'", size: 10 },
              callback: (v) => `${v}%`
            }
          }
        }
      }
    });

    legendBox.innerHTML = `
      <div class="legend-item"><span class="legend-color-box" style="background:${activeColor};"></span> ${activeName}: Max DD <strong>${activeMinDd.toFixed(2)}%</strong></div>
      ${otherDdLegend}
      ${sbDdLegend}
      <div class="legend-item"><span class="legend-color-box" style="background:#A855F7;"></span> NDX: Max DD <strong>${ndxMinDd.toFixed(2)}%</strong></div>
      <div class="legend-item"><span class="legend-color-box" style="background:#F43F5E;"></span> TQQQ: Max DD <strong class="text-rose">${tqqqMinDd.toFixed(2)}%</strong></div>
    `;

  } else if (currentTab === "technicals") {
    // --- TAB 2: NDX PRICE VS SMAS ---
    const ndxPrice = plotRecords.map(r => r.ndx_price);
    const sma50 = plotRecords.map(r => r.sma50);
    const sma250 = plotRecords.map(r => r.sma250);

    chartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "NDX Price",
            data: ndxPrice,
            borderColor: "#FFFFFF",
            borderWidth: 2,
            fill: false,
            tension: 0.2,
            pointRadius: plotRecords.length > 60 ? 0 : 3,
          },
          {
            label: "50-Day SMA (Exit Line)",
            data: sma50,
            borderColor: "#F59E0B",
            borderWidth: 2,
            borderDash: [4, 4],
            fill: false,
            tension: 0.1,
            pointRadius: 0,
          },
          {
            label: "250-Day SMA (Regime Line)",
            data: sma250,
            borderColor: "#A855F7",
            borderWidth: 2,
            borderDash: [6, 6],
            fill: false,
            tension: 0.1,
            pointRadius: 0,
          }
        ]
      },
      options: getCommonChartOptions("")
    });

    legendBox.innerHTML = `
      <div class="legend-item"><span class="legend-color-box" style="background:#FFFFFF;"></span> NDX Close</div>
      <div class="legend-item"><span class="legend-color-box" style="background:#F59E0B;"></span> 50-Day SMA (Exit Threshold)</div>
      <div class="legend-item"><span class="legend-color-box" style="background:#A855F7;"></span> 250-Day SMA (Bull/Bear Macro)</div>
    `;

  } else if (currentTab === "rsi") {
    // --- TAB 3: RSI(14) MOMENTUM ---
    const rsiData = plotRecords.map(r => r.rsi);
    const rsi75 = plotRecords.map(() => 75);
    const rsi50 = plotRecords.map(() => 50);
    const rsi30 = plotRecords.map(() => 30);

    const gradPink = ctx.createLinearGradient(0, 0, 0, 350);
    gradPink.addColorStop(0, "rgba(244, 63, 94, 0.25)");
    gradPink.addColorStop(1, "rgba(244, 63, 94, 0.0)");

    chartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "RSI(14)",
            data: rsiData,
            borderColor: "#F43F5E",
            borderWidth: 2,
            backgroundColor: gradPink,
            fill: true,
            tension: 0.25,
            pointRadius: plotRecords.length > 60 ? 0 : 3,
          },
          {
            label: "Overbought (75)",
            data: rsi75,
            borderColor: "rgba(244, 63, 94, 0.6)",
            borderWidth: 1.5,
            borderDash: [4, 4],
            fill: false,
            pointRadius: 0,
          },
          {
            label: "Midline (50)",
            data: rsi50,
            borderColor: "rgba(255, 255, 255, 0.2)",
            borderWidth: 1,
            borderDash: [2, 2],
            fill: false,
            pointRadius: 0,
          },
          {
            label: "Oversold (30)",
            data: rsi30,
            borderColor: "rgba(0, 242, 254, 0.6)",
            borderWidth: 1.5,
            borderDash: [4, 4],
            fill: false,
            pointRadius: 0,
          }
        ]
      },
      options: {
        ...getCommonChartOptions(""),
        scales: {
          ...getCommonChartOptions("").scales,
          y: {
            min: 15,
            max: 90,
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: { color: "#94A3B8", font: { family: "'JetBrains Mono'", size: 10 } }
          }
        }
      }
    });

    legendBox.innerHTML = `
      <div class="legend-item"><span class="legend-color-box" style="background:#F43F5E;"></span> RSI(14) Momentum</div>
      <div class="legend-item"><span class="legend-color-box" style="background:rgba(244,63,94,0.6);"></span> Overbought (75 Trim Line)</div>
      <div class="legend-item"><span class="legend-color-box" style="background:rgba(0,242,254,0.6);"></span> Oversold (30 Floor)</div>
    `;
  }
}

function getCommonChartOptions(prefix = "") {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "#0D111A",
        borderColor: "rgba(0, 242, 254, 0.3)",
        borderWidth: 1,
        titleColor: "#00F2FE",
        bodyColor: "#F1F5F9",
        titleFont: { family: "'JetBrains Mono'", size: 12, weight: "bold" },
        bodyFont: { family: "'JetBrains Mono'", size: 11 },
        padding: 12,
        boxPadding: 6,
        callbacks: {
          label: function(context) {
            let val = context.raw;
            if (prefix === "$") {
              const diffPct = ((val / simulatedCapital) - 1) * 100;
              const sign = diffPct >= 0 ? "+" : "";
              return `${context.dataset.label}: $${val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${sign}${diffPct.toFixed(2)}%)`;
            } else if (prefix === "%") {
              return `${context.dataset.label}: ${val.toFixed(2)}% from peak`;
            } else {
              return `${context.dataset.label}: ${val.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 2 })}`;
            }
          }
        }
      }
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: {
          color: "#64748B",
          font: { family: "'JetBrains Mono'", size: 10 },
          maxRotation: 0,
          autoSkip: true,
          maxTicksLimit: 10
        }
      },
      y: {
        grid: { color: "rgba(255, 255, 255, 0.04)" },
        ticks: {
          color: "#94A3B8",
          font: { family: "'JetBrains Mono'", size: 10 },
          callback: function(value) {
            if (prefix === "$") {
              if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
              if (value >= 1000) return `$${(value / 1000).toFixed(0)}k`;
              return `$${value}`;
            }
            if (prefix === "%") return `${value}%`;
            return value.toLocaleString();
          }
        }
      }
    }
  };
}

/* ==========================================================================
   6. COMPLETED TRADE CYCLES ENGINE & TABLE INSPECTOR
   ========================================================================== */
function computeTradeCycles(trades) {
  if (!trades || trades.length === 0) return [];
  const cycles = [];
  let cur = null;

  for (let i = 0; i < trades.length; i++) {
    const t = trades[i];
    const act = (t.action || "").toUpperCase();

    if (act === "BUY" && cur === null) {
      cur = {
        cycleNum: cycles.length + 1,
        entryDate: t.date,
        ticker: t.ticker,
        entryPrice: parseFloat(t.price) || 0,
        entryVal: parseFloat(t.value) || 0,
        entryNdx: parseFloat(t.ndx_price) || 0,
        exitDate: null,
        exitPrice: 0,
        exitVal: 0,
        exitNdx: 0,
        exitReason: "",
        durationDays: 0,
        pnlDollar: 0,
        pnlPct: 0,
        outcome: "OPEN"
      };
    } else if (act === "SELL" && cur !== null) {
      cur.exitDate = t.date;
      cur.exitPrice = parseFloat(t.price) || 0;
      cur.exitVal = parseFloat(t.value) || 0;
      cur.exitNdx = parseFloat(t.ndx_price) || 0;
      cur.exitReason = t.reason || "System signal exit";

      const d1 = new Date(cur.entryDate);
      const d2 = new Date(cur.exitDate);
      cur.durationDays = Math.max(1, Math.round((d2 - d1) / (1000 * 60 * 60 * 24)));

      cur.pnlDollar = cur.exitVal - cur.entryVal;
      cur.pnlPct = cur.entryVal > 0 ? ((cur.exitVal / cur.entryVal) - 1) * 100 : 0;
      cur.outcome = cur.pnlDollar >= 0 ? "WIN" : "LOSS";

      cycles.push(cur);
      cur = null;
    }
  }

  return cycles;
}

function renderTradesTable(trades) {
  applyTradeFilters();
}

function applyTradeFilters() {
  if (!cachedData) return;

  const activeModelObj = (cachedData.models && cachedData.models[currentModel]) ? cachedData.models[currentModel] : cachedData;
  const tradesPool = activeModelObj.trades || cachedData.trades;
  if (!tradesPool) return;

  const baseStartCap = (activeModelObj.portfolio && activeModelObj.portfolio.starting_capital) || 10000;
  const scaleFactor = simulatedCapital / baseStartCap;

  const actionFilter = document.getElementById("tradeActionFilter");
  const yearFilter = document.getElementById("tradeYearFilter");
  const searchInput = document.getElementById("tradeSearchInput");

  const actionVal = actionFilter ? actionFilter.value : "ALL";
  const yearVal = yearFilter ? yearFilter.value : "ALL";
  const query = searchInput ? searchInput.value.toLowerCase().trim() : "";

  // Dynamic filter dropdown options update for current view
  if (actionFilter) {
    if (currentTradeView === "cycles") {
      actionFilter.innerHTML = `
        <option value="ALL">All Outcomes</option>
        <option value="WIN">WIN Trades</option>
        <option value="LOSS">LOSS Trades</option>
      `;
      actionFilter.value = ["ALL", "WIN", "LOSS"].includes(actionVal) ? actionVal : "ALL";
    } else {
      actionFilter.innerHTML = `
        <option value="ALL">All Actions</option>
        <option value="BUY">BUY (100%)</option>
        <option value="SELL">SELL / CASH</option>
        <option value="ADJUST">TRIM (30%/50%)</option>
      `;
      actionFilter.value = ["ALL", "BUY", "SELL", "ADJUST"].includes(actionVal) ? actionVal : "ALL";
    }
  }

  // Populate Year Filter options
  if (yearFilter && yearFilter.options.length <= 1) {
    const years = [...new Set(tradesPool.map(t => (t.date || "").substring(0, 4)).filter(Boolean))].sort().reverse();
    years.forEach(yr => {
      const opt = document.createElement("option");
      opt.value = yr;
      opt.textContent = yr;
      yearFilter.appendChild(opt);
    });
  }

  const tableHead = document.getElementById("tradeTableHead");
  const tbody = document.getElementById("tradeTableBody");
  const cyclesSummaryBar = document.getElementById("cyclesSummaryBar");

  const allCycles = computeTradeCycles(tradesPool);
  const countCyclesEl = document.getElementById("countCycles");
  if (countCyclesEl) countCyclesEl.textContent = allCycles.length;

  const countExecutionsEl = document.getElementById("countExecutions");
  if (countExecutionsEl) countExecutionsEl.textContent = tradesPool.length;

  if (currentTradeView === "cycles") {
    // --- CYCLES VIEW ---
    if (cyclesSummaryBar) cyclesSummaryBar.style.display = "flex";

    // Update Summary Bar
    const wins = allCycles.filter(c => c.pnlDollar > 0);
    const losses = allCycles.filter(c => c.pnlDollar <= 0);
    const winRate = allCycles.length > 0 ? (wins.length / allCycles.length * 100) : 0;
    const grossProfit = wins.reduce((acc, c) => acc + c.pnlDollar, 0);
    const grossLoss = Math.abs(losses.reduce((acc, c) => acc + c.pnlDollar, 0));
    const pf = grossLoss > 0 ? (grossProfit / grossLoss) : 0;
    const avgWin = wins.length > 0 ? (wins.reduce((acc, c) => acc + c.pnlPct, 0) / wins.length) : 0;
    const avgLoss = losses.length > 0 ? (losses.reduce((acc, c) => acc + c.pnlPct, 0) / losses.length) : 0;
    const totalDays = allCycles.reduce((acc, c) => acc + c.durationDays, 0);
    const avgDur = allCycles.length > 0 ? Math.round(totalDays / allCycles.length) : 0;

    const elCycles = document.getElementById("csbCycles");
    if (elCycles) elCycles.textContent = `${allCycles.length} completed`;
    const elWinRate = document.getElementById("csbWinRate");
    if (elWinRate) elWinRate.textContent = `${winRate.toFixed(1)}% (${wins.length}W / ${losses.length}L)`;
    const elPf = document.getElementById("csbProfitFactor");
    if (elPf) elPf.textContent = `${pf.toFixed(2)}×`;
    const elAvgWin = document.getElementById("csbAvgWin");
    if (elAvgWin) elAvgWin.textContent = `+${avgWin.toFixed(1)}%`;
    const elAvgLoss = document.getElementById("csbAvgLoss");
    if (elAvgLoss) elAvgLoss.textContent = `${avgLoss.toFixed(1)}%`;
    const elAvgDur = document.getElementById("csbAvgDuration");
    if (elAvgDur) elAvgDur.textContent = `${avgDur} days`;

    // Filter Cycles
    let filteredCycles = [...allCycles];
    if (actionVal !== "ALL") {
      filteredCycles = filteredCycles.filter(c => c.outcome === actionVal);
    }
    if (yearVal !== "ALL") {
      filteredCycles = filteredCycles.filter(c => (c.entryDate || "").startsWith(yearVal) || (c.exitDate || "").startsWith(yearVal));
    }
    if (query) {
      filteredCycles = filteredCycles.filter(c => {
        const rowStr = `${c.cycleNum} ${c.entryDate} ${c.exitDate} ${c.ticker} ${c.outcome} ${c.exitReason}`.toLowerCase();
        return rowStr.includes(query);
      });
    }

    if (tableHead) {
      tableHead.innerHTML = `
        <tr>
          <th>Cycle</th>
          <th>Entry Date</th>
          <th>Exit Date</th>
          <th>Hold Time</th>
          <th>Ticker</th>
          <th>Entry Cap</th>
          <th>Exit Cap</th>
          <th>Realized Return</th>
          <th>Outcome</th>
          <th>Exit Catalyst</th>
        </tr>
      `;
    }

    if (filteredCycles.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted">No completed trade cycles match selected filters.</td></tr>`;
      return;
    }

    // Newest cycles first
    const sorted = [...filteredCycles].reverse();
    tbody.innerHTML = sorted.map(c => {
      const isWin = c.pnlDollar >= 0;
      return `
        <tr>
          <td><strong>#${c.cycleNum}</strong></td>
          <td>${c.entryDate} ($${c.entryPrice.toFixed(2)})</td>
          <td>${c.exitDate} ($${c.exitPrice.toFixed(2)})</td>
          <td>${c.durationDays} days</td>
          <td><strong>${c.ticker}</strong></td>
          <td>${formatCurrency(c.entryVal * scaleFactor)}</td>
          <td><strong>${formatCurrency(c.exitVal * scaleFactor)}</strong></td>
          <td class="${isWin ? 'text-emerald' : 'text-rose'} font-mono">
            ${isWin ? '+' : ''}${formatCurrency(c.pnlDollar * scaleFactor)} (${isWin ? '+' : ''}${c.pnlPct.toFixed(2)}%)
          </td>
          <td><span class="outcome-pill ${isWin ? 'outcome-win' : 'outcome-loss'}">${c.outcome}</span></td>
          <td><span class="trade-reason-text" title="${c.exitReason}">${c.exitReason}</span></td>
        </tr>
      `;
    }).join("");

  } else {
    // --- RAW EXECUTIONS VIEW ---
    if (cyclesSummaryBar) cyclesSummaryBar.style.display = "none";

    let filtered = [...tradesPool];
    if (actionVal !== "ALL") {
      filtered = filtered.filter(t => (t.action || "").toUpperCase().includes(actionVal));
    }
    if (yearVal !== "ALL") {
      filtered = filtered.filter(t => (t.date || "").startsWith(yearVal));
    }
    if (query) {
      filtered = filtered.filter(t => {
        const rowStr = `${t.date} ${t.action} ${t.ticker} ${t.reason}`.toLowerCase();
        return rowStr.includes(query);
      });
    }

    if (tableHead) {
      tableHead.innerHTML = `
        <tr>
          <th>Date</th>
          <th>Action</th>
          <th>Ticker</th>
          <th>Shares</th>
          <th>Execution Price</th>
          <th>Total Value</th>
          <th>NDX Level</th>
          <th>Reason</th>
        </tr>
      `;
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">No raw executions match selected filters.</td></tr>`;
      return;
    }

    const sorted = [...filtered].reverse();
    tbody.innerHTML = sorted.slice(0, 300).map(t => {
      let actionClass = "action-adjust";
      if (t.action === "BUY") actionClass = "action-buy";
      if (t.action === "SELL") actionClass = "action-sell";

      const shares = (parseFloat(t.shares) || 0) * scaleFactor;
      const price = parseFloat(t.price) || 0;
      const value = (parseFloat(t.value) || 0) * scaleFactor;
      const ndx = parseFloat(t.ndx_price) || 0;

      return `
        <tr>
          <td>${t.date || "N/A"}</td>
          <td><span class="action-pill ${actionClass}">${t.action}</span></td>
          <td><strong>${t.ticker}</strong></td>
          <td>${shares.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</td>
          <td>$${price.toFixed(2)}</td>
          <td><strong>${formatCurrency(value)}</strong></td>
          <td>${ndx.toLocaleString("en-US", { minimumFractionDigits: 1 })}</td>
          <td><span class="trade-reason-text" title="${t.reason}">${t.reason}</span></td>
        </tr>
      `;
    }).join("");
  }
}

/* ==========================================================================
   7. CSV EXPORT TOOLING
   ========================================================================== */
function exportCurrentTradeData() {
  if (!cachedData) return;

  const activeModelObj = (cachedData.models && cachedData.models[currentModel]) ? cachedData.models[currentModel] : cachedData;
  const tradesPool = activeModelObj.trades || cachedData.trades;
  if (!tradesPool || tradesPool.length === 0) {
    alert("No trade data available to export.");
    return;
  }

  const baseStartCap = (activeModelObj.portfolio && activeModelObj.portfolio.starting_capital) || 10000;
  const scaleFactor = simulatedCapital / baseStartCap;

  let csvContent = "";
  let filename = "";

  if (currentTradeView === "cycles") {
    const cycles = computeTradeCycles(tradesPool);
    filename = `ndx_strategy_cycles_${currentModel}_${Date.now()}.csv`;
    const headers = ["Cycle_ID", "Entry_Date", "Exit_Date", "Holding_Days", "Ticker", "Entry_Price", "Exit_Price", "Invested_Capital", "Exit_Proceeds", "Realized_PnL_Dollar", "Return_Pct", "Outcome", "Exit_Catalyst"];
    csvContent = headers.join(",") + "\n";

    cycles.forEach(c => {
      const row = [
        c.cycleNum,
        `"${c.entryDate}"`,
        `"${c.exitDate}"`,
        c.durationDays,
        `"${c.ticker}"`,
        c.entryPrice.toFixed(2),
        c.exitPrice.toFixed(2),
        (c.entryVal * scaleFactor).toFixed(2),
        (c.exitVal * scaleFactor).toFixed(2),
        (c.pnlDollar * scaleFactor).toFixed(2),
        c.pnlPct.toFixed(2),
        `"${c.outcome}"`,
        `"${(c.exitReason || "").replace(/"/g, '""')}"`
      ];
      csvContent += row.join(",") + "\n";
    });

  } else {
    filename = `ndx_strategy_executions_${currentModel}_${Date.now()}.csv`;
    const headers = ["Date", "Timestamp", "Action", "Ticker", "Shares", "Price", "Scaled_Value", "NDX_Price", "SMA50", "SMA250", "RSI", "Reason"];
    csvContent = headers.join(",") + "\n";

    tradesPool.forEach(t => {
      const shares = (parseFloat(t.shares) || 0) * scaleFactor;
      const value = (parseFloat(t.value) || 0) * scaleFactor;
      const row = [
        `"${t.date || ""}"`,
        `"${t.timestamp || ""}"`,
        `"${t.action || ""}"`,
        `"${t.ticker || ""}"`,
        shares.toFixed(4),
        (parseFloat(t.price) || 0).toFixed(2),
        value.toFixed(2),
        (parseFloat(t.ndx_price) || 0).toFixed(2),
        (parseFloat(t.sma50) || 0).toFixed(2),
        (parseFloat(t.sma250) || 0).toFixed(2),
        (parseFloat(t.rsi) || 0).toFixed(2),
        `"${(t.reason || "").replace(/"/g, '""')}"`
      ];
      csvContent += row.join(",") + "\n";
    });
  }

  // Trigger download
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);

  showToast(`Exported ${currentTradeView === 'cycles' ? 'completed cycles' : 'trade executions'} to CSV!`);
}

/* ==========================================================================
   8. STRATEGY LOG TERMINAL STREAM
   ========================================================================== */
function renderTerminal(logs) {
  const win = document.getElementById("terminalWindow");
  if (!logs || logs.length === 0 || !win) return;

  const html = logs.map(line => {
    let colored = line;
    if (line.includes("[INFO]")) {
      colored = colored.replace("[INFO]", `<span class="log-info">[INFO]</span>`);
    }
    if (line.includes("TRADE SIGNAL") || line.includes("Bought") || line.includes("Sold")) {
      colored = `<span class="log-trade">${colored}</span>`;
    }
    return `<div class="term-line">${colored}</div>`;
  }).join("");

  win.innerHTML = html;
  win.scrollTop = win.scrollHeight;
}

/* ==========================================================================
   9. TIME & MARKET STATUS HELPERS
   ========================================================================== */
function updateClocks() {
  const now = new Date();
  
  // Format MT and EST
  const timeMT = now.toLocaleTimeString("en-US", { timeZone: "America/Denver", hour12: false });
  const timeEST = now.toLocaleTimeString("en-US", { timeZone: "America/New_York", hour12: false });
  
  const elMT = document.getElementById("clockTimeMT");
  if (elMT) elMT.textContent = `${timeMT} MT`;
  const elEST = document.getElementById("clockTimeEST");
  if (elEST) elEST.textContent = `${timeEST} EST`;

  // Countdown timer to 1:50 PM MT (13:50)
  updateCountdown();
}

function updateCountdown() {
  const timerEl = document.getElementById("countdownTimer");
  if (!timerEl) return;

  const now = new Date();
  const nyseNow = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  
  let target = new Date(nyseNow);
  target.setHours(15, 50, 0, 0); // 3:50 PM EST = 1:50 PM MT

  if (nyseNow >= target) {
    target.setDate(target.getDate() + 1);
  }

  // Skip Saturday / Sunday
  if (target.getDay() === 6) target.setDate(target.getDate() + 2);
  if (target.getDay() === 0) target.setDate(target.getDate() + 1);

  const diffMs = target - nyseNow;
  if (diffMs <= 0) {
    timerEl.textContent = "RUNNING NOW";
    return;
  }

  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  const mins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
  const secs = Math.floor((diffMs % (1000 * 60)) / 1000);

  timerEl.textContent = `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function updateMarketStatus() {
  const pill = document.getElementById("marketStatusPill");
  const label = document.getElementById("marketStatusText");
  if (!pill || !label) return;

  const now = new Date();
  const nyse = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const day = nyse.getDay();
  const hours = nyse.getHours();
  const mins = nyse.getMinutes();
  const totalMins = hours * 60 + mins;

  const openMins = 9 * 60 + 30; // 9:30 AM
  const closeMins = 16 * 60;    // 4:00 PM

  if (day === 0 || day === 6) {
    pill.className = "market-status-pill closed";
    label.textContent = "WEEKEND CLOSED";
  } else if (totalMins >= openMins && totalMins < closeMins) {
    pill.className = "market-status-pill open";
    label.textContent = "NYSE OPEN";
  } else {
    pill.className = "market-status-pill after-hours";
    label.textContent = "AFTER-HOURS";
  }
}

function formatCurrency(val) {
  if (isNaN(val)) return "$0.00";
  return "$" + val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/* ==========================================================================
   10. QUANT LAB: CLIENT-SIDE SIMULATION ENGINE & SANDBOX BACKTEST
   ========================================================================== */
function runClientSideSimulation() {
  const modelObj = (cachedData && cachedData.models && cachedData.models.symmetric_atr) ? cachedData.models.symmetric_atr : cachedData;
  const allDaily = (modelObj && modelObj.daily_summary) || (cachedData && cachedData.daily_summary) || [];
  
  if (!allDaily || allDaily.length < 50) {
    showToast("Strategy data not yet loaded. Please wait.", "fa-solid fa-clock text-amber");
    return;
  }

  // 1. Read Controls
  const capInput = parseFloat(document.getElementById("sbCapital").value) || 10000;
  const startDate = document.getElementById("sbStartDate").value || "2010-02-11";
  const endDate = document.getElementById("sbEndDate").value || "2026-03-30";
  const smaPeriod = parseInt(document.getElementById("sbSmaPeriod").value, 10) || 50;
  const bufferType = document.getElementById("sbBufferType").value;
  const rsiTrim = document.getElementById("sbRsiTrim").value;
  const bearAsset = document.getElementById("sbBearAsset").value;

  // 2. Identify date indexes
  let startIndex = allDaily.findIndex(r => r.date >= startDate);
  if (startIndex === -1) startIndex = 0;
  
  let endIndex = allDaily.length - 1;
  for (let i = allDaily.length - 1; i >= 0; i--) {
    if (allDaily[i].date <= endDate) {
      endIndex = i;
      break;
    }
  }

  if (endIndex <= startIndex) {
    showToast("Invalid date range selected for simulation!", "fa-solid fa-triangle-exclamation text-rose");
    return;
  }

  // 3. Precompute rolling SMA for NDX across all records
  const customSmas = new Array(allDaily.length);
  let rollingSum = 0;
  for (let i = 0; i < allDaily.length; i++) {
    rollingSum += allDaily[i].ndx_price;
    if (i >= smaPeriod) {
      rollingSum -= allDaily[i - smaPeriod].ndx_price;
      customSmas[i] = rollingSum / smaPeriod;
    } else {
      customSmas[i] = rollingSum / (i + 1);
    }
  }

  // 4. Determine buffer and RSI parameters
  let bufferPct = 0;
  let isAtr = false;
  let atrMult = 1.0;
  if (bufferType === "atr_1_0") { isAtr = true; atrMult = 1.0; }
  else if (bufferType === "atr_0_5") { isAtr = true; atrMult = 0.5; }
  else if (bufferType === "atr_1_5") { isAtr = true; atrMult = 1.5; }
  else if (bufferType === "fixed_1_0") { bufferPct = 0.01; }
  else if (bufferType === "fixed_2_0") { bufferPct = 0.02; }
  else if (bufferType === "fixed_0_0") { bufferPct = 0.0; }

  let rsiThreshold = 999;
  let trimFraction = 0;
  if (rsiTrim === "75_25") { rsiThreshold = 75; trimFraction = 0.25; }
  else if (rsiTrim === "80_25") { rsiThreshold = 80; trimFraction = 0.25; }
  else if (rsiTrim === "75_50") { rsiThreshold = 75; trimFraction = 0.50; }

  // 5. Run Day-by-Day Simulation
  const rfDaily = Math.pow(1 + 0.045, 1 / 252) - 1;
  let curCapital = capInput;
  let position = "CASH";
  let tqqqWeight = 0;
  const simResults = [];
  const cycles = [];
  let activeCycle = null;

  for (let i = startIndex; i <= endIndex; i++) {
    const cur = allDaily[i];
    const prev = i > 0 ? allDaily[i - 1] : cur;

    // Daily percentage changes
    const tqqqPrevPnl = prev.tqqq_buyhold_pnl_pct || 0;
    const tqqqCurPnl = cur.tqqq_buyhold_pnl_pct || 0;
    const rTqqq = (1 + tqqqCurPnl / 100) / (1 + tqqqPrevPnl / 100) - 1;
    const rNdx = prev.ndx_price > 0 ? (cur.ndx_price - prev.ndx_price) / prev.ndx_price : 0;

    // Bear asset return
    let rBear = rfDaily;
    if (bearAsset === "sqqq_50") {
      rBear = 0.5 * rfDaily + 0.5 * (-3 * rNdx);
    } else if (bearAsset === "sqqq_100") {
      rBear = -3 * rNdx;
    }

    // Apply asset returns based on prior day's holding
    if (i > startIndex) {
      if (position === "TQQQ") {
        const tqqqVal = curCapital * tqqqWeight * (1 + rTqqq);
        const bearVal = curCapital * (1 - tqqqWeight) * (1 + rBear);
        curCapital = Math.max(0.01, tqqqVal + bearVal);
      } else {
        curCapital = Math.max(0.01, curCapital * (1 + rBear));
      }
    }

    // Evaluate signals on today's close
    const smaVal = customSmas[i];
    let exitBuffer = 0;
    let entryBuffer = 0;
    if (isAtr) {
      const estAtr = cur.ndx_price * 0.013;
      exitBuffer = atrMult * estAtr;
      entryBuffer = 0;
    } else {
      exitBuffer = smaVal * bufferPct;
      entryBuffer = smaVal * bufferPct;
    }

    const ndxPrice = cur.ndx_price;
    const rsi = cur.rsi || 50;

    if (position === "CASH") {
      if (ndxPrice > (smaVal + entryBuffer)) {
        position = "TQQQ";
        tqqqWeight = (rsi > rsiThreshold) ? (1 - trimFraction) : 1.0;
        activeCycle = { entryDate: cur.date, entryCapital: curCapital, entryNdx: ndxPrice };
      }
    } else if (position === "TQQQ") {
      if (ndxPrice < (smaVal - exitBuffer)) {
        position = "CASH";
        tqqqWeight = 0;
        if (activeCycle) {
          const pnlDollar = curCapital - activeCycle.entryCapital;
          const pnlPct = (pnlDollar / activeCycle.entryCapital) * 100;
          cycles.push({
            entryDate: activeCycle.entryDate,
            exitDate: cur.date,
            pnlDollar,
            pnlPct
          });
          activeCycle = null;
        }
      } else {
        tqqqWeight = (rsi > rsiThreshold) ? (1 - trimFraction) : 1.0;
      }
    }

    simResults.push({
      date: cur.date,
      total_value: curCapital,
      position: position,
      ndx_price: cur.ndx_price,
      tqqq_buyhold_pnl_pct: cur.tqqq_buyhold_pnl_pct
    });
  }

  // Close active cycle if still open at end
  if (activeCycle) {
    const pnlDollar = curCapital - activeCycle.entryCapital;
    const pnlPct = (pnlDollar / activeCycle.entryCapital) * 100;
    cycles.push({
      entryDate: activeCycle.entryDate,
      exitDate: simResults[simResults.length - 1].date,
      pnlDollar,
      pnlPct
    });
  }

  // 6. Compute Quant Risk & Performance Metrics
  const finalVal = curCapital;
  const totalReturnPct = ((finalVal / capInput) - 1) * 100;
  const nYears = simResults.length / 252;
  const cagr = nYears > 0 ? (Math.pow(finalVal / capInput, 1 / nYears) - 1) * 100 : 0;

  // Daily returns for Sharpe
  const dailyReturns = [];
  for (let j = 1; j < simResults.length; j++) {
    dailyReturns.push((simResults[j].total_value - simResults[j - 1].total_value) / simResults[j - 1].total_value);
  }
  const meanRet = dailyReturns.reduce((a, b) => a + b, 0) / (dailyReturns.length || 1);
  const varRet = dailyReturns.reduce((a, b) => a + Math.pow(b - meanRet, 2), 0) / (dailyReturns.length || 1);
  const stdRet = Math.sqrt(varRet);
  const sharpe = stdRet > 0 ? (Math.sqrt(252) * (meanRet - rfDaily) / stdRet) : 0;

  // Maximum Drawdown
  let hwm = capInput;
  let maxDd = 0;
  simResults.forEach(r => {
    if (r.total_value > hwm) hwm = r.total_value;
    const dd = ((r.total_value - hwm) / hwm) * 100;
    if (dd < maxDd) maxDd = dd;
  });

  // Cycle Win Rate
  const wins = cycles.filter(c => c.pnlDollar > 0);
  const winRate = cycles.length > 0 ? (wins.length / cycles.length) * 100 : 0;

  // 7. Benchmark Reference (Symmetric 1.0x ATR)
  const benchDaily = (cachedData && cachedData.models && cachedData.models.symmetric_atr && cachedData.models.symmetric_atr.daily_summary) || allDaily;
  const bSlice = benchDaily.filter(r => r.date >= startDate && r.date <= endDate);
  let benchVal = capInput * 44.6;
  let benchRet = 4360.9;
  let benchCagr = 25.7;
  let benchSharpe = 0.64;
  let benchMaxDd = -52.3;
  let benchWinRate = 47.5;
  let benchCycleCount = 84;

  if (bSlice.length >= 2) {
    const bStart = bSlice[0].total_value;
    const bEnd = bSlice[bSlice.length - 1].total_value;
    benchVal = capInput * (bEnd / bStart);
    benchRet = ((bEnd / bStart) - 1) * 100;
    const bYears = bSlice.length / 252;
    benchCagr = bYears > 0 ? (Math.pow(bEnd / bStart, 1 / bYears) - 1) * 100 : 0;
    
    let bHwm = bSlice[0].total_value;
    let bDd = 0;
    bSlice.forEach(r => {
      if (r.total_value > bHwm) bHwm = r.total_value;
      const d = ((r.total_value - bHwm) / bHwm) * 100;
      if (d < bDd) bDd = d;
    });
    benchMaxDd = bDd;
  }

  // 8. Update Scorecard DOM
  const elResVal = document.getElementById("sbResValue");
  if (elResVal) elResVal.textContent = formatCurrency(finalVal);
  const elBenchVal = document.getElementById("sbBenchValue");
  if (elBenchVal) elBenchVal.textContent = `Benchmark: ${formatCurrency(benchVal)}`;

  const elResRet = document.getElementById("sbResReturn");
  if (elResRet) elResRet.textContent = `${totalReturnPct >= 0 ? '+' : ''}${totalReturnPct.toFixed(1)}%`;
  const elBenchRet = document.getElementById("sbBenchReturn");
  if (elBenchRet) elBenchRet.textContent = `Benchmark: ${benchRet >= 0 ? '+' : ''}${benchRet.toFixed(1)}%`;

  const elResCagr = document.getElementById("sbResCagr");
  if (elResCagr) elResCagr.textContent = `${cagr >= 0 ? '+' : ''}${cagr.toFixed(1)}%`;
  const elBenchCagr = document.getElementById("sbBenchCagr");
  if (elBenchCagr) elBenchCagr.textContent = `Benchmark: ${benchCagr >= 0 ? '+' : ''}${benchCagr.toFixed(1)}%`;

  const elResSharpe = document.getElementById("sbResSharpe");
  if (elResSharpe) elResSharpe.textContent = sharpe.toFixed(2);
  const elBenchSharpe = document.getElementById("sbBenchSharpe");
  if (elBenchSharpe) elBenchSharpe.textContent = `Benchmark: ${benchSharpe.toFixed(2)}`;

  const elResMaxDd = document.getElementById("sbResMaxDd");
  if (elResMaxDd) elResMaxDd.textContent = `${maxDd.toFixed(1)}%`;
  const elBenchMaxDd = document.getElementById("sbBenchMaxDd");
  if (elBenchMaxDd) elBenchMaxDd.textContent = `Benchmark: ${benchMaxDd.toFixed(1)}%`;

  const elResWin = document.getElementById("sbResWinRate");
  if (elResWin) elResWin.textContent = `${winRate.toFixed(1)}% (${wins.length}W / ${cycles.length - wins.length}L)`;
  const elBenchWin = document.getElementById("sbBenchWinRate");
  if (elBenchWin) elBenchWin.textContent = `Benchmark: ${benchWinRate.toFixed(1)}% (${benchCycleCount} Cycles)`;

  // 9. Draw preview chart
  renderSandboxPreviewChart(simResults);

  // Store in global memory for Overlay & CSV export
  window._lastSandboxResult = {
    name: `Sandbox Model (SMA${smaPeriod}, ${bufferType.replace(/_/g, ' ')})`,
    records: simResults,
    cycles: cycles,
    metrics: { finalVal, totalReturnPct, cagr, sharpe, maxDd, winRate }
  };
}

/* ==========================================================================
   11. SANDBOX PREVIEW MINI-CHART
   ========================================================================== */
function renderSandboxPreviewChart(simRecords) {
  const canvas = document.getElementById("sbPreviewChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  if (sbPreviewChartInstance) {
    sbPreviewChartInstance.destroy();
  }

  // Sample to max 150 points for smooth canvas rendering in modal
  let dataPoints = simRecords;
  if (dataPoints.length > 150) {
    const step = Math.ceil(dataPoints.length / 150);
    const sampled = [];
    for (let i = 0; i < dataPoints.length; i += step) {
      sampled.push(dataPoints[i]);
    }
    if (sampled[sampled.length - 1] !== dataPoints[dataPoints.length - 1]) {
      sampled.push(dataPoints[dataPoints.length - 1]);
    }
    dataPoints = sampled;
  }

  const labels = dataPoints.map(r => r.date);
  const values = dataPoints.map(r => r.total_value);

  const grad = ctx.createLinearGradient(0, 0, 0, 200);
  grad.addColorStop(0, "rgba(168, 85, 247, 0.35)");
  grad.addColorStop(1, "rgba(0, 242, 254, 0.0)");

  sbPreviewChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Sandbox Equity",
          data: values,
          borderColor: "#C084FC",
          borderWidth: 2,
          backgroundColor: grad,
          fill: true,
          pointRadius: 0,
          tension: 0.15
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: "index",
          intersect: false,
          callbacks: {
            label: (ctx) => `Portfolio: $${ctx.parsed.y.toLocaleString("en-US", { maximumFractionDigits: 0 })}`
          }
        }
      },
      scales: {
        x: {
          display: true,
          grid: { display: false },
          ticks: { color: "#64748B", font: { family: "JetBrains Mono", size: 10 }, maxTicksLimit: 6 }
        },
        y: {
          display: true,
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: {
            color: "#64748B",
            font: { family: "JetBrains Mono", size: 10 },
            callback: (v) => `$${(v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v)}`
          }
        }
      }
    }
  });
}

/* ==========================================================================
   12. SANDBOX CSV EXPORT
   ========================================================================== */
function exportSandboxCsv() {
  if (!window._lastSandboxResult || !window._lastSandboxResult.records) {
    showToast("No simulation data to export! Click 'Run Simulation' first.", "fa-solid fa-triangle-exclamation text-amber");
    return;
  }
  const records = window._lastSandboxResult.records;
  let csv = "Date,Portfolio_Value,Position,NDX_Price,TQQQ_PnL_Pct\n";
  records.forEach(r => {
    csv += `${r.date},${r.total_value.toFixed(2)},${r.position},${r.ndx_price.toFixed(2)},${(r.tqqq_buyhold_pnl_pct || 0).toFixed(2)}\n`;
  });

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `sandbox_simulation_${records[0].date}_to_${records[records.length - 1].date}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast("Simulation CSV exported successfully!");
}
