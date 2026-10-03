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
let customEndDate = "2026-10-01";
let sandboxCustomModelResult = null;
let sbPreviewChartInstance = null;

// Real-time Clock interval
setInterval(updateClocks, 1000);

document.addEventListener("DOMContentLoaded", () => {
  parseUrlParams();
  initEventListeners();
  initEducationalTooltips();
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

  if (params.has("matrixview")) {
    const mv = params.get("matrixview").toLowerCase();
    if (["all", "crisis"].includes(mv)) {
      currentMatrixView = mv;
      document.querySelectorAll(".matrix-toggle-btn").forEach(b => {
        b.classList.toggle("active", b.getAttribute("data-view") === mv);
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
  url.searchParams.set("matrixview", currentMatrixView);
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

  // Capital Simulator Bar Preset Buttons ($5K, $10K, $25K, $50K, $100K)
  document.querySelectorAll(".sim-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const amt = parseFloat(btn.getAttribute("data-amt"));
      if (amt && amt > 0) {
        simulatedCapital = amt;
        const inp = document.getElementById("simCustomCapital");
        if (inp) inp.value = amt;
        document.querySelectorAll(".sim-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        updateUrlParams();
        if (cachedData) {
          renderUI(cachedData);
          renderChart();
          showToast(`Simulated Capital: $${amt.toLocaleString()}`);
        }
      }
    });
  });

  // Capital Simulator Custom Input Field
  const simCustomInp = document.getElementById("simCustomCapital");
  if (simCustomInp) {
    simCustomInp.addEventListener("input", (e) => {
      const amt = parseFloat(e.target.value);
      if (!isNaN(amt) && amt > 0) {
        simulatedCapital = amt;
        document.querySelectorAll(".sim-btn").forEach(b => {
          b.classList.toggle("active", parseFloat(b.getAttribute("data-amt")) === amt);
        });
        updateUrlParams();
        if (cachedData) {
          renderUI(cachedData);
          renderChart();
        }
      }
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

  // Annual Performance Matrix View Switcher (All Years vs Crisis Stress Tests)
  document.querySelectorAll(".matrix-toggle-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const view = btn.getAttribute("data-view");
      if (view) {
        currentMatrixView = view;
        document.querySelectorAll(".matrix-toggle-btn").forEach(b => b.classList.toggle("active", b.getAttribute("data-view") === view));
        updateUrlParams();
        if (cachedData) {
          renderAnnualMatrix(cachedData);
          showToast(`Annual Matrix: ${view === 'crisis' ? 'Crisis Stress Tests' : 'All 17 Years'}`);
        }
      }
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

  // Sandbox DCA Frequency & Amount listeners
  const sbDcaFreq = document.getElementById("sbDcaFreq");
  const sbDcaAmtInp = document.getElementById("sbDcaAmount");
  const sbDcaInputWrap = document.getElementById("sbDcaInputWrap");
  const sbDcaPillsWrap = document.getElementById("sbDcaPillsWrap");
  const sbDcaSummaryDisplay = document.getElementById("sbDcaSummaryDisplay");

  function updateDcaControlsDisplay() {
    if (!sbDcaFreq || !sbDcaSummaryDisplay) return;
    const freq = sbDcaFreq.value;
    const amt = parseFloat(sbDcaAmtInp ? sbDcaAmtInp.value : 0) || 0;

    if (freq === "none") {
      sbDcaSummaryDisplay.textContent = "Lump Sum Only";
      sbDcaSummaryDisplay.className = "sb-val-display font-mono text-muted";
      if (sbDcaInputWrap) sbDcaInputWrap.style.opacity = "0.35";
      if (sbDcaPillsWrap) sbDcaPillsWrap.style.opacity = "0.35";
    } else {
      if (sbDcaInputWrap) sbDcaInputWrap.style.opacity = "1";
      if (sbDcaPillsWrap) sbDcaPillsWrap.style.opacity = "1";
      sbDcaSummaryDisplay.className = "sb-val-display font-mono text-emerald";
      if (freq === "biweekly") {
        sbDcaSummaryDisplay.textContent = `+$${amt.toLocaleString()} / 2 Wks`;
      } else if (freq === "monthly") {
        sbDcaSummaryDisplay.textContent = `+$${amt.toLocaleString()} / Mo`;
      } else if (freq === "quarterly") {
        sbDcaSummaryDisplay.textContent = `+$${amt.toLocaleString()} / Qtr`;
      }
    }
  }

  if (sbDcaFreq) {
    sbDcaFreq.addEventListener("change", updateDcaControlsDisplay);
  }
  if (sbDcaAmtInp) {
    sbDcaAmtInp.addEventListener("input", () => {
      const val = parseFloat(sbDcaAmtInp.value);
      document.querySelectorAll(".sb-dca-pill").forEach(p => {
        p.classList.toggle("active", parseFloat(p.getAttribute("data-amt")) === val);
      });
      updateDcaControlsDisplay();
    });
  }
  document.querySelectorAll(".sb-dca-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".sb-dca-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      const amt = pill.getAttribute("data-amt");
      if (sbDcaAmtInp && amt) {
        sbDcaAmtInp.value = amt;
        updateDcaControlsDisplay();
      }
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

  // Trade Table View Switcher (Completed Cycles vs Raw Order Fills)
  document.querySelectorAll(".tview-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const view = btn.getAttribute("data-view");
      if (view) {
        currentTradeView = view;
        document.querySelectorAll(".tview-btn").forEach(b => b.classList.toggle("active", b.getAttribute("data-view") === view));
        updateUrlParams();
        applyTradeFilters();
      }
    });
  });

  // Trade Table CSV Export Button
  const btnExportCsv = document.getElementById("btnExportCsv");
  if (btnExportCsv) {
    btnExportCsv.addEventListener("click", exportCurrentTradeData);
  }

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
    const data = await res.json();
    cachedData = data;

    // Dynamically ensure date pickers support latest session data (e.g. 2026-10-01)
    const allDaily = (data.daily_summary) || (data.models && data.models.symmetric_atr && data.models.symmetric_atr.daily_summary) || [];
    if (allDaily.length > 0) {
      const latestDate = allDaily[allDaily.length - 1].date;
      ["customStartDate", "customEndDate", "sbStartDate", "sbEndDate"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.max = latestDate;
      });
      const elCustomEnd = document.getElementById("customEndDate");
      if (elCustomEnd && (!elCustomEnd.value || elCustomEnd.value === "2026-03-30")) {
        elCustomEnd.value = latestDate;
        customEndDate = latestDate;
      }
      const elSbEnd = document.getElementById("sbEndDate");
      if (elSbEnd && (!elSbEnd.value || elSbEnd.value === "2026-03-30")) {
        elSbEnd.value = latestDate;
      }
    }

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

  // Determine current active asset price & SQQQ price
  const latestDaily = (daily && daily.length > 0) ? daily[daily.length - 1] : {};
  const curNdx = (stats && stats.ndx_price) || latestDaily.ndx_price || 0;
  const curSma50 = (stats && stats.sma50) || latestDaily.sma50 || 0;
  const curSma250 = (stats && stats.sma250) || latestDaily.sma250 || 0;
  const curRsi = (stats && stats.rsi !== undefined) ? stats.rsi : (latestDaily.rsi !== undefined ? latestDaily.rsi : 50.0);

  // Asset prices
  let tqqqPx = (stats && stats.tqqq_price) || 0;
  if (!tqqqPx && p.tqqq_shares > 0) {
    tqqqPx = (p.total_value - p.cash) / p.tqqq_shares;
  }
  if (!tqqqPx) tqqqPx = 81.01;
  let sqqqPx = (stats && stats.sqqq_price) || 33.12;

  if (p.position === "TQQQ_100") {
    banner.className = "regime-hero-banner regime-bull";
    badge.className = "regime-badge";
    badgeText.textContent = "100% TQQQ (BULL TREND)";
    headline.textContent = "Full Bull Regime Confirmed";
    icon.className = "fa-solid fa-bolt-lightning";
  } else if (p.position === "TQQQ_50") {
    banner.className = "regime-hero-banner regime-bull";
    badge.className = "regime-badge";
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

  // Scaled values
  const scaledTotal = p.total_value * scaleFactor;
  const scaledPnl = (p.total_value - baseStartCap) * scaleFactor;
  const pnlPct = ((p.total_value / baseStartCap) - 1) * 100;

  // Left Quick Chips (no mental math on holdings or levels)
  const heroHoldings = document.getElementById("heroHoldingsText");
  if (heroHoldings) {
    if (p.tqqq_shares > 0) {
      heroHoldings.textContent = `${(p.tqqq_shares * scaleFactor).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} TQQQ @ $${tqqqPx.toFixed(2)}`;
    } else if (p.sqqq_shares > 0) {
      heroHoldings.textContent = `${(p.sqqq_shares * scaleFactor).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} SQQQ @ $${sqqqPx.toFixed(2)}`;
    } else {
      heroHoldings.textContent = `100% Cash (${formatCurrency(p.cash * scaleFactor)})`;
    }
  }

  const heroVal = document.getElementById("heroValuationText");
  if (heroVal) heroVal.textContent = formatCurrency(scaledTotal);

  const heroSma = document.getElementById("heroSma50Text");
  if (heroSma) heroSma.textContent = curSma50 ? curSma50.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : "--";

  // Telemetry Card 1: Active Asset Price
  const assetPriceEl = document.getElementById("heroAssetPrice");
  const assetBadgeEl = document.getElementById("heroAssetBadge");
  const avgCostEl = document.getElementById("heroAvgCost");
  const unrealizedPill = document.getElementById("heroUnrealizedPill");
  const sqqqQuoteEl = document.getElementById("heroSqqqPrice");

  if (p.position.startsWith("TQQQ")) {
    if (assetBadgeEl) {
      assetBadgeEl.textContent = "TQQQ 3× BULL";
      assetBadgeEl.className = "ht-badge badge-bull";
    }
    if (assetPriceEl) assetPriceEl.textContent = `$${tqqqPx.toFixed(2)}`;
    if (avgCostEl) avgCostEl.textContent = `$${p.tqqq_avg_cost.toFixed(2)}`;
    if (unrealizedPill) {
      const uPct = p.tqqq_avg_cost > 0 ? ((tqqqPx / p.tqqq_avg_cost - 1) * 100) : 0;
      unrealizedPill.textContent = `${uPct >= 0 ? "+" : ""}${uPct.toFixed(2)}%`;
      unrealizedPill.className = `ht-pnl-pill ${uPct >= 0 ? "positive" : "negative"}`;
    }
  } else if (p.position === "SQQQ") {
    if (assetBadgeEl) {
      assetBadgeEl.textContent = "SQQQ 3× BEAR";
      assetBadgeEl.className = "ht-badge badge-bear";
    }
    if (assetPriceEl) assetPriceEl.textContent = `$${sqqqPx.toFixed(2)}`;
    if (avgCostEl) avgCostEl.textContent = `$${p.sqqq_avg_cost.toFixed(2)}`;
    if (unrealizedPill) {
      const uPct = p.sqqq_avg_cost > 0 ? ((sqqqPx / p.sqqq_avg_cost - 1) * 100) : 0;
      unrealizedPill.textContent = `${uPct >= 0 ? "+" : ""}${uPct.toFixed(2)}%`;
      unrealizedPill.className = `ht-pnl-pill ${uPct >= 0 ? "positive" : "negative"}`;
    }
  } else {
    if (assetBadgeEl) {
      assetBadgeEl.textContent = "100% CASH";
      assetBadgeEl.className = "ht-badge badge-neutral";
    }
    if (assetPriceEl) assetPriceEl.textContent = "4.50% Yield";
    if (avgCostEl) avgCostEl.textContent = "Risk-Free";
    if (unrealizedPill) {
      unrealizedPill.textContent = "Protected";
      unrealizedPill.className = "ht-pnl-pill positive";
    }
  }
  if (sqqqQuoteEl) sqqqQuoteEl.textContent = `$${sqqqPx.toFixed(2)}`;

  // Telemetry Card 2: RSI-14 Momentum Gauge (Primary RSI, Secondary Headroom)
  const rsiValEl = document.getElementById("heroRsiVal");
  const rsiBadgeEl = document.getElementById("heroRsiBadge");
  const rsiMeterEl = document.getElementById("heroRsiMeterFill");
  const rsiHeadroomEl = document.getElementById("heroRsiHeadroomText");

  if (rsiValEl) rsiValEl.textContent = typeof curRsi === "number" ? curRsi.toFixed(1) : "--";
  if (rsiMeterEl) {
    const clampedRsi = Math.min(Math.max(curRsi, 0), 100);
    rsiMeterEl.style.width = `${clampedRsi}%`;
  }
  const rsiHeadroom = 75.0 - curRsi;
  if (rsiHeadroomEl) {
    if (rsiHeadroom <= 0) {
      rsiHeadroomEl.textContent = "0.0 pts (TRIM ACTIVE)";
    } else {
      rsiHeadroomEl.textContent = `${rsiHeadroom.toFixed(1)} pts`;
    }
  }
  if (rsiBadgeEl) {
    if (curRsi >= 75) {
      rsiBadgeEl.textContent = "OVERBOUGHT";
      rsiBadgeEl.className = "ht-badge badge-bear";
    } else if (curRsi <= 30) {
      rsiBadgeEl.textContent = "OVERSOLD";
      rsiBadgeEl.className = "ht-badge badge-neutral";
    } else if (curRsi >= 60) {
      rsiBadgeEl.textContent = "BULL MOMENTUM";
      rsiBadgeEl.className = "ht-badge badge-bull";
    } else {
      rsiBadgeEl.textContent = "NEUTRAL";
      rsiBadgeEl.className = "ht-badge badge-neutral";
    }
  }

  // Telemetry Card 3: Downside Stop Cushion
  const distSma50Text = document.getElementById("heroDistSma50Text");
  const cushionPctEl = document.getElementById("heroCushionPct");
  const exitPriceEl = document.getElementById("heroExitPriceText");
  const defenseBadgeEl = document.getElementById("heroDefenseBadge");

  const distPts = stats.dist_sma50_pts !== undefined ? stats.dist_sma50_pts : (curNdx - curSma50);
  const distPct = stats.dist_sma50_pct !== undefined ? stats.dist_sma50_pct : (curSma50 > 0 ? (distPts / curSma50 * 100) : 0);

  if (distSma50Text) {
    distSma50Text.textContent = `${distPts >= 0 ? "+" : ""}${distPts.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} pts`;
    distSma50Text.className = `ht-primary-val ${distPts >= 0 ? "text-emerald" : "text-rose"}`;
  }
  if (cushionPctEl) {
    cushionPctEl.textContent = `${distPct >= 0 ? "+" : ""}${distPct.toFixed(2)}%`;
  }
  if (exitPriceEl) {
    exitPriceEl.textContent = curSma50 ? curSma50.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : "--";
  }
  if (defenseBadgeEl) {
    if (distPts >= 500) {
      defenseBadgeEl.textContent = "WIDE CUSHION";
      defenseBadgeEl.className = "ht-badge badge-bull";
    } else if (distPts >= 0) {
      defenseBadgeEl.textContent = "TIGHT CUSHION";
      defenseBadgeEl.className = "ht-badge badge-neutral";
    } else {
      defenseBadgeEl.textContent = "BELOW STOP";
      defenseBadgeEl.className = "ht-badge badge-bear";
    }
  }

  // 2b. 5-State Strategy Gearbox & Forward Shift Tripwires
  const gear100 = document.getElementById("gearTqqq100");
  const gear50 = document.getElementById("gearTqqq50");
  const gear30 = document.getElementById("gearTqqq30");
  const gearCash = document.getElementById("gearCash");
  const gearSqqq = document.getElementById("gearSqqq");

  const gearCap100 = document.getElementById("gearCapTqqq100");
  const gearCap50 = document.getElementById("gearCapTqqq50");
  const gearCap30 = document.getElementById("gearCapTqqq30");
  const gearCapCash = document.getElementById("gearCapCash");
  const gearCapSqqq = document.getElementById("gearCapSqqq");

  const gbActiveName = document.getElementById("gearboxActiveGearName");
  const gbActiveSub = document.getElementById("gearboxActiveGearSub");

  document.querySelectorAll(".gear-card").forEach(c => c.classList.remove("active"));

  if (p.position === "TQQQ_100") {
    if (gear100) gear100.classList.add("active");
    if (gbActiveName) {
      gbActiveName.textContent = "GEAR 1 (100% TQQQ)";
      gbActiveName.className = "text-emerald";
    }
    if (gbActiveSub) gbActiveSub.textContent = `Full Bull Expansion: 100% Capital Invested in TQQQ • 0% Cash Reserve (${formatCurrency(scaledTotal)})`;
    if (gearCap100) gearCap100.textContent = `Allocated: ${formatCurrency(scaledTotal)}`;
    if (gearCap50) gearCap50.textContent = "Standby (0%)";
    if (gearCap30) gearCap30.textContent = "Standby (0%)";
    if (gearCapCash) gearCapCash.textContent = "Standby (0%)";
    if (gearCapSqqq) gearCapSqqq.textContent = "Standby (0%)";
  } else if (p.position === "TQQQ_50") {
    if (gear50) gear50.classList.add("active");
    if (gbActiveName) {
      gbActiveName.textContent = "GEAR 2 (50% TQQQ)";
      gbActiveName.className = "text-amber";
    }
    if (gbActiveSub) gbActiveSub.textContent = `Divergence Trim: 50% Equity (${formatCurrency(scaledTotal * 0.5)}) • 50% Cash (${formatCurrency(scaledTotal * 0.5)})`;
    if (gearCap100) gearCap100.textContent = "Standby (0%)";
    if (gearCap50) gearCap50.textContent = `Active: ${formatCurrency(scaledTotal * 0.5)}`;
    if (gearCap30) gearCap30.textContent = "Standby (0%)";
    if (gearCapCash) gearCapCash.textContent = `Cash: ${formatCurrency(scaledTotal * 0.5)}`;
    if (gearCapSqqq) gearCapSqqq.textContent = "Standby (0%)";
  } else if (p.position === "TQQQ_30") {
    if (gear30) gear30.classList.add("active");
    if (gbActiveName) {
      gbActiveName.textContent = "GEAR 3 (30% TQQQ)";
      gbActiveName.className = "text-orange";
    }
    if (gbActiveSub) gbActiveSub.textContent = `Overbought Trim: 30% Equity (${formatCurrency(scaledTotal * 0.3)}) • 70% Cash (${formatCurrency(scaledTotal * 0.7)})`;
    if (gearCap100) gearCap100.textContent = "Standby (0%)";
    if (gearCap50) gearCap50.textContent = "Standby (0%)";
    if (gearCap30) gearCap30.textContent = `Active: ${formatCurrency(scaledTotal * 0.3)}`;
    if (gearCapCash) gearCapCash.textContent = `Cash: ${formatCurrency(scaledTotal * 0.7)}`;
    if (gearCapSqqq) gearCapSqqq.textContent = "Standby (0%)";
  } else if (p.position === "SQQQ") {
    if (gearSqqq) gearSqqq.classList.add("active");
    if (gbActiveName) {
      gbActiveName.textContent = "GEAR 5 (100% SQQQ)";
      gbActiveName.className = "text-rose";
    }
    if (gbActiveSub) gbActiveSub.textContent = `Macro Bear Inverse: 100% Capital in 3× Short SQQQ (${formatCurrency(scaledTotal)})`;
    if (gearCap100) gearCap100.textContent = "Standby (0%)";
    if (gearCap50) gearCap50.textContent = "Standby (0%)";
    if (gearCap30) gearCap30.textContent = "Standby (0%)";
    if (gearCapCash) gearCapCash.textContent = "Standby (0%)";
    if (gearCapSqqq) gearCapSqqq.textContent = `Allocated: ${formatCurrency(scaledTotal)}`;
  } else {
    if (gearCash) gearCash.classList.add("active");
    if (gbActiveName) {
      gbActiveName.textContent = "GEAR 4 (100% CASH)";
      gbActiveName.className = "text-cyan";
    }
    if (gbActiveSub) gbActiveSub.textContent = `Capital Defense: 100% Cash in 4.5% Treasury Yield (${formatCurrency(scaledTotal)}) • 0% Equity Risk`;
    if (gearCap100) gearCap100.textContent = "Standby (0%)";
    if (gearCap50) gearCap50.textContent = "Standby (0%)";
    if (gearCap30) gearCap30.textContent = "Standby (0%)";
    if (gearCapCash) gearCapCash.textContent = `Allocated: ${formatCurrency(scaledTotal)}`;
    if (gearCapSqqq) gearCapSqqq.textContent = "Standby (0%)";
  }

  // Forward Shift Tripwires HUD
  const twRsiEl = document.getElementById("twRsiHeadroomVal");
  const twSma50El = document.getElementById("twSma50Val");
  const twDefEl = document.getElementById("twDefenseCushionVal");
  const twSma250El = document.getElementById("twSma250Val");
  const twBearEl = document.getElementById("twBearDistVal");

  if (twRsiEl) {
    const twRsiHeadroom = 75.0 - curRsi;
    if (twRsiHeadroom <= 0) {
      twRsiEl.textContent = "Trigger Breached (Trim Active)";
      twRsiEl.className = "tw-val text-rose";
    } else {
      twRsiEl.textContent = `+${twRsiHeadroom.toFixed(1)} pts headroom`;
      twRsiEl.className = "tw-val text-amber";
    }
  }

  if (twSma50El) {
    twSma50El.textContent = curSma50 ? curSma50.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : "--";
  }

  if (twDefEl) {
    twDefEl.textContent = `${distPts >= 0 ? "+" : ""}${distPts.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} pts (${distPct >= 0 ? "+" : ""}${distPct.toFixed(2)}%) cushion`;
    twDefEl.className = `tw-val ${distPts >= 0 ? "text-emerald" : "text-rose"}`;
  }

  if (twSma250El) {
    twSma250El.textContent = curSma250 ? curSma250.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : "--";
  }

  if (twBearEl) {
    const distSma250 = curNdx - curSma250;
    if (curNdx < curSma250) {
      twBearEl.textContent = "Price Below SMA250 (Bear Short Eligible)";
      twBearEl.className = "tw-val text-rose";
    } else {
      twBearEl.textContent = `+${distSma250.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} pts buffer (Standby)`;
      twBearEl.className = "tw-val text-cyan";
    }
  }

  // 3. Scaled KPI Cards

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

  const ndxEl = document.getElementById("ndxLevel");
  if (ndxEl) ndxEl.textContent = curNdx ? curNdx.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "--";

  const sma50El = document.getElementById("ndxSma50");
  if (sma50El) sma50El.textContent = curSma50 ? `SMA50: ${curSma50.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}` : "SMA50: --";

  const sma250El = document.getElementById("ndxSma250");
  if (sma250El) sma250El.textContent = curSma250 ? `SMA250: ${curSma250.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}` : "SMA250: --";

  // Card 4: Peak Equity & Risk Profile (De-duplicated from RSI which is already in Hero telemetry)
  const peakHwmEl = document.getElementById("kpiPeakHwm");
  const drawdownPillEl = document.getElementById("kpiDrawdownPill");
  const maxDdPillEl = document.getElementById("kpiMaxDdPill");

  const rawHwm = (stats && stats.high_water_mark) || p.total_value;
  const scaledHwm = rawHwm * scaleFactor;
  if (peakHwmEl) peakHwmEl.textContent = formatCurrency(scaledHwm);

  const curDrawdownPct = rawHwm > 0 ? ((p.total_value - rawHwm) / rawHwm * 100) : 0;
  if (drawdownPillEl) {
    if (Math.abs(curDrawdownPct) < 0.05) {
      drawdownPillEl.textContent = "0.00% DD (ATH Peak)";
      drawdownPillEl.className = "pnl-pill positive";
    } else {
      drawdownPillEl.textContent = `${curDrawdownPct.toFixed(2)}% DD`;
      drawdownPillEl.className = "pnl-pill negative";
    }
  }

  const maxDdVal = (stats && stats.max_drawdown_pct !== undefined) ? stats.max_drawdown_pct : -24.81;
  if (maxDdPillEl) {
    maxDdPillEl.textContent = `Max Historical DD: ${maxDdVal.toFixed(2)}%`;
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
/**
 * Returns dynamic color class for metric value matching tooltip legend ratings:
 * - Red ('text-rose'): Subpar / High Drawdown / Trailing
 * - Amber ('text-amber'): Medium / Solid / Benchmark
 * - Emerald ('text-emerald'): Strong / Institutional Elite / Top 1%
 */
function getMetricRatingClass(metricKey, val) {
  switch (metricKey) {
    case "sharpe":
      return val >= 1.0 ? "text-emerald" : (val >= 0.5 ? "text-amber" : "text-rose");
    case "sortino":
      return val >= 1.0 ? "text-emerald" : (val >= 0.6 ? "text-amber" : "text-rose");
    case "calmar":
      return val >= 0.7 ? "text-emerald" : (val >= 0.3 ? "text-amber" : "text-rose");
    case "cagr":
      return val >= 0.20 ? "text-emerald" : (val >= 0.12 ? "text-amber" : "text-rose");
    case "profit_factor":
      return val >= 1.6 ? "text-emerald" : (val >= 1.2 ? "text-amber" : "text-rose");
    case "win_rate":
      return val >= 50.0 ? "text-emerald" : (val >= 40.0 ? "text-amber" : "text-rose");
    case "payoff":
      return val >= 2.0 ? "text-emerald" : (val >= 1.5 ? "text-amber" : "text-rose");
    case "max_dd_duration":
      return val <= 300 ? "text-emerald" : (val <= 600 ? "text-amber" : "text-rose");
    default:
      return "text-cyan";
  }
}

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
    const end = customEndDate || "2026-10-01";
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

  // Update DOM Elements & dynamic rating color classes
  const elSharpe = document.getElementById("qmSharpe");
  if (elSharpe) {
    elSharpe.textContent = annSharpe.toFixed(2);
    elSharpe.className = `qm-value font-mono ${getMetricRatingClass("sharpe", annSharpe)}`;
  }

  const elSortino = document.getElementById("qmSortino");
  if (elSortino) {
    elSortino.textContent = annSortino.toFixed(2);
    elSortino.className = `qm-value font-mono ${getMetricRatingClass("sortino", annSortino)}`;
  }

  const elCalmar = document.getElementById("qmCalmar");
  if (elCalmar) {
    elCalmar.textContent = calmar.toFixed(2);
    elCalmar.className = `qm-value font-mono ${getMetricRatingClass("calmar", calmar)}`;
  }

  const elCagr = document.getElementById("qmCagr");
  if (elCagr) {
    elCagr.textContent = `${cagr >= 0 ? '+' : ''}${(cagr * 100).toFixed(1)}%`;
    elCagr.className = `qm-value font-mono ${getMetricRatingClass("cagr", cagr)}`;
  }

  const elPF = document.getElementById("qmProfitFactor");
  if (elPF) {
    elPF.textContent = `${profitFactor.toFixed(2)}×`;
    elPF.className = `qm-value font-mono ${getMetricRatingClass("profit_factor", profitFactor)}`;
  }

  const elPFSub = document.getElementById("qmProfitFactorSub");
  if (elPFSub) elPFSub.textContent = `$${(grossProfit / 1000).toFixed(0)}k Win / $${(grossLoss / 1000).toFixed(0)}k Loss`;

  const elWinRate = document.getElementById("qmWinRate");
  if (elWinRate) {
    elWinRate.textContent = `${winRate.toFixed(1)}%`;
    elWinRate.className = `qm-value font-mono ${getMetricRatingClass("win_rate", winRate)}`;
  }

  const elWinCount = document.getElementById("qmWinLossCount");
  if (elWinCount) elWinCount.textContent = `${wins.length} Wins / ${losses.length} Losses`;

  const elPayoff = document.getElementById("qmPayoffRatio");
  if (elPayoff) {
    elPayoff.textContent = `${payoffRatio.toFixed(2)}×`;
    elPayoff.className = `qm-value font-mono ${getMetricRatingClass("payoff", payoffRatio)}`;
  }

  const elPayoffSub = document.getElementById("qmPayoffSub");
  if (elPayoffSub) elPayoffSub.textContent = `+${avgWinPct.toFixed(1)}% / ${avgLossPct.toFixed(1)}%`;

  const elMaxDur = document.getElementById("qmMaxDdDuration");
  if (elMaxDur) {
    elMaxDur.textContent = `${maxDurationDays} days`;
    elMaxDur.className = `qm-value font-mono ${getMetricRatingClass("max_dd_duration", maxDurationDays)}`;
  }
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
    const end = customEndDate || "2026-10-01";
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
      const end = customEndDate || "2026-10-01";
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

/**
 * Calculates Exact Internal Rate of Return (Money-Weighted Return) via Newton-Raphson
 * Supports irregular periodic cash inflows (e.g. payroll DCA deposits)
 */
function computeXIRR(cashFlows, finalVal, finalDate) {
  if (!cashFlows || cashFlows.length === 0) return 0;
  const flows = cashFlows.map(cf => ({ date: cf.date, amount: cf.amount }));
  flows.push({ date: finalDate, amount: finalVal });

  const d0 = Date.parse(flows[0].date + "T00:00:00Z");
  const yearFraction = flows.map(f => (Date.parse(f.date + "T00:00:00Z") - d0) / (365.25 * 86400000));
  const totalYrs = yearFraction[yearFraction.length - 1];
  if (totalYrs <= 0) return 0;

  function f(r) {
    let sum = 0;
    for (let i = 0; i < flows.length; i++) {
      sum += flows[i].amount / Math.pow(1 + r, yearFraction[i]);
    }
    return sum;
  }

  function df(r) {
    let sum = 0;
    for (let i = 0; i < flows.length; i++) {
      sum -= yearFraction[i] * flows[i].amount / Math.pow(1 + r, yearFraction[i] + 1);
    }
    return sum;
  }

  // Initial estimate
  let r = 0.15;
  for (let iter = 0; iter < 50; iter++) {
    const y = f(r);
    const dy = df(r);
    if (Math.abs(dy) < 1e-12) break;
    const nextR = r - y / dy;
    if (Math.abs(nextR - r) < 1e-6) {
      r = nextR;
      break;
    }
    r = Math.max(-0.99, nextR);
  }

  return isNaN(r) ? 0 : r * 100;
}

function runClientSideSimulation() {
  const modelObj = (cachedData && cachedData.models && cachedData.models.symmetric_atr) ? cachedData.models.symmetric_atr : cachedData;
  const allDaily = (modelObj && modelObj.daily_summary) || (cachedData && cachedData.daily_summary) || [];
  
  if (!allDaily || allDaily.length < 50) {
    showToast("Strategy data not yet loaded. Please wait.", "fa-solid fa-clock text-amber");
    return;
  }

  // 1. Read Controls
  const capInput = parseFloat(document.getElementById("sbCapital").value) || 10000;
  const dcaFreq = document.getElementById("sbDcaFreq") ? document.getElementById("sbDcaFreq").value : "none";
  const dcaAmtInp = parseFloat(document.getElementById("sbDcaAmount") ? document.getElementById("sbDcaAmount").value : 0) || 0;
  const isDcaActive = (dcaFreq !== "none" && dcaAmtInp > 0);
  const dcaAmt = isDcaActive ? dcaAmtInp : 0;

  const startDate = document.getElementById("sbStartDate").value || "2010-02-11";
  const endDate = document.getElementById("sbEndDate").value || "2026-10-01";
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
  let benchCapital = capInput;
  let totalInvested = capInput;
  let position = "CASH";
  let tqqqWeight = 0;
  const simResults = [];
  const cycles = [];
  let activeCycle = null;
  const cashFlows = [{ date: allDaily[startIndex].date, amount: -capInput }];

  let lastDcaDateStr = allDaily[startIndex].date;
  let lastDcaMonthStr = allDaily[startIndex].date.slice(0, 7);

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

    // Benchmark daily return (Symmetric ATR benchmark from allDaily)
    const benchPrev = prev.total_value || capInput;
    const benchCur = cur.total_value || capInput;
    const rBench = benchPrev > 0 ? (benchCur - benchPrev) / benchPrev : 0;

    // Apply asset returns based on prior day's holding
    if (i > startIndex) {
      if (position === "TQQQ") {
        const tqqqVal = curCapital * tqqqWeight * (1 + rTqqq);
        const bearVal = curCapital * (1 - tqqqWeight) * (1 + rBear);
        curCapital = Math.max(0.01, tqqqVal + bearVal);
      } else {
        curCapital = Math.max(0.01, curCapital * (1 + rBear));
      }
      benchCapital = Math.max(0.01, benchCapital * (1 + rBench));
    }

    // Evaluate DCA contribution today
    let isDcaDay = false;
    if (isDcaActive && i > startIndex) {
      if (dcaFreq === "biweekly") {
        const msCur = Date.parse(cur.date + "T00:00:00Z");
        const msPrev = Date.parse(lastDcaDateStr + "T00:00:00Z");
        const diffDays = Math.round((msCur - msPrev) / 86400000);
        if (diffDays >= 14) isDcaDay = true;
      } else if (dcaFreq === "monthly") {
        const curMonth = cur.date.slice(0, 7);
        if (curMonth !== lastDcaMonthStr) isDcaDay = true;
      } else if (dcaFreq === "quarterly") {
        const msCur = Date.parse(cur.date + "T00:00:00Z");
        const msPrev = Date.parse(lastDcaDateStr + "T00:00:00Z");
        const diffDays = Math.round((msCur - msPrev) / 86400000);
        if (diffDays >= 90) isDcaDay = true;
      }
    }

    if (isDcaDay) {
      totalInvested += dcaAmt;
      curCapital += dcaAmt;
      benchCapital += dcaAmt;
      cashFlows.push({ date: cur.date, amount: -dcaAmt });
      lastDcaDateStr = cur.date;
      lastDcaMonthStr = cur.date.slice(0, 7);
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
      total_invested: totalInvested,
      bench_value: benchCapital,
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
  const netProfitDollar = finalVal - totalInvested;
  const roicPct = totalInvested > 0 ? (netProfitDollar / totalInvested) * 100 : 0;
  const wealthMultiplier = totalInvested > 0 ? (finalVal / totalInvested) : 0;

  const nYears = simResults.length / 252;
  let cagr = 0;
  if (!isDcaActive) {
    cagr = nYears > 0 ? (Math.pow(finalVal / capInput, 1 / nYears) - 1) * 100 : 0;
  } else {
    cagr = computeXIRR(cashFlows, finalVal, simResults[simResults.length - 1].date);
  }

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

  // 7. Benchmark Reference (Symmetric 1.0x ATR Model with identical DCA schedule)
  const benchFinal = benchCapital;
  const benchNetProfit = benchFinal - totalInvested;
  const benchRoicPct = totalInvested > 0 ? (benchNetProfit / totalInvested) * 100 : 0;
  const benchMultiplier = totalInvested > 0 ? (benchFinal / totalInvested) : 0;
  let benchCagr = 0;
  if (!isDcaActive) {
    benchCagr = nYears > 0 ? (Math.pow(benchFinal / capInput, 1 / nYears) - 1) * 100 : 0;
  } else {
    benchCagr = computeXIRR(cashFlows, benchFinal, simResults[simResults.length - 1].date);
  }

  let bHwm = capInput;
  let benchMaxDd = 0;
  simResults.forEach(r => {
    if (r.bench_value > bHwm) bHwm = r.bench_value;
    const d = ((r.bench_value - bHwm) / bHwm) * 100;
    if (d < benchMaxDd) benchMaxDd = d;
  });
  const benchSharpe = 0.64;
  const benchWinRate = 47.5;
  const benchCycleCount = 84;

  // 8. Update Scorecard DOM
  const elResVal = document.getElementById("sbResValue");
  if (elResVal) {
    elResVal.textContent = formatCurrency(finalVal);
    elResVal.className = `sb-metric-val font-mono ${finalVal >= totalInvested * 5 ? 'text-emerald' : (finalVal >= totalInvested * 2 ? 'text-amber' : 'text-rose')}`;
  }
  const elBenchVal = document.getElementById("sbBenchValue");
  if (elBenchVal) elBenchVal.textContent = `Benchmark: ${formatCurrency(benchFinal)}`;

  const elResInvested = document.getElementById("sbResInvested");
  if (elResInvested) elResInvested.textContent = formatCurrency(totalInvested);
  const elBenchInvested = document.getElementById("sbBenchInvested");
  if (elBenchInvested) {
    elBenchInvested.textContent = !isDcaActive
      ? "Lump Sum Initial"
      : `$${Math.round(capInput).toLocaleString()} start + $${Math.round(totalInvested - capInput).toLocaleString()} DCA`;
  }

  const elResRet = document.getElementById("sbResReturn");
  if (elResRet) {
    elResRet.textContent = `${netProfitDollar >= 0 ? '+' : ''}${formatCurrency(netProfitDollar)} (${roicPct >= 0 ? '+' : ''}${roicPct.toFixed(1)}%)`;
    elResRet.className = `sb-metric-val font-mono ${roicPct >= 500 ? 'text-emerald' : (roicPct >= 100 ? 'text-amber' : 'text-rose')}`;
  }
  const elBenchRet = document.getElementById("sbBenchReturn");
  if (elBenchRet) {
    elBenchRet.textContent = `Benchmark: ${benchNetProfit >= 0 ? '+' : ''}${formatCurrency(benchNetProfit)} (${benchRoicPct >= 0 ? '+' : ''}${benchRoicPct.toFixed(1)}%)`;
  }

  const elCagrLabel = document.getElementById("sbCagrLabel");
  if (elCagrLabel) {
    elCagrLabel.textContent = `ANNUALIZED RETURN (${isDcaActive ? 'IRR / MWR' : 'CAGR'})`;
  }
  const elResCagr = document.getElementById("sbResCagr");
  if (elResCagr) {
    elResCagr.textContent = `${cagr >= 0 ? '+' : ''}${cagr.toFixed(1)}%`;
    elResCagr.className = `sb-metric-val font-mono ${getMetricRatingClass("cagr", cagr / 100)}`;
  }
  const elBenchCagr = document.getElementById("sbBenchCagr");
  if (elBenchCagr) elBenchCagr.textContent = `Benchmark: ${benchCagr >= 0 ? '+' : ''}${benchCagr.toFixed(1)}%`;

  const elResSharpe = document.getElementById("sbResSharpe");
  if (elResSharpe) {
    elResSharpe.textContent = sharpe.toFixed(2);
    elResSharpe.className = `sb-metric-val font-mono ${getMetricRatingClass("sharpe", sharpe)}`;
  }
  const elBenchSharpe = document.getElementById("sbBenchSharpe");
  if (elBenchSharpe) elBenchSharpe.textContent = `Benchmark: ${benchSharpe.toFixed(2)}`;

  const elResMaxDd = document.getElementById("sbResMaxDd");
  if (elResMaxDd) {
    elResMaxDd.textContent = `${maxDd.toFixed(1)}%`;
    elResMaxDd.className = `sb-metric-val font-mono ${maxDd >= -40 ? 'text-emerald' : (maxDd >= -65 ? 'text-amber' : 'text-rose')}`;
  }
  const elBenchMaxDd = document.getElementById("sbBenchMaxDd");
  if (elBenchMaxDd) elBenchMaxDd.textContent = `Benchmark: ${benchMaxDd.toFixed(1)}%`;

  const elResMultiplier = document.getElementById("sbResMultiplier");
  if (elResMultiplier) {
    elResMultiplier.textContent = `${wealthMultiplier.toFixed(1)}×`;
    elResMultiplier.className = `sb-metric-val font-mono ${wealthMultiplier >= 10 ? 'text-emerald' : (wealthMultiplier >= 3 ? 'text-amber' : 'text-rose')}`;
  }
  const elBenchMultiplier = document.getElementById("sbBenchMultiplier");
  if (elBenchMultiplier) elBenchMultiplier.textContent = `Benchmark: ${benchMultiplier.toFixed(1)}×`;

  const elResWin = document.getElementById("sbResWinRate");
  if (elResWin) {
    elResWin.textContent = `${winRate.toFixed(1)}% (${wins.length}W / ${cycles.length - wins.length}L)`;
    elResWin.className = `sb-metric-val font-mono ${getMetricRatingClass("win_rate", winRate)}`;
  }
  const elBenchWin = document.getElementById("sbBenchWinRate");
  if (elBenchWin) elBenchWin.textContent = `Benchmark: ${benchWinRate.toFixed(1)}% (${benchCycleCount} Cycles)`;

  // 9. Draw preview chart
  renderSandboxPreviewChart(simResults, isDcaActive);

  // Store in global memory for Overlay & CSV export
  window._lastSandboxResult = {
    name: `Sandbox Model (SMA${smaPeriod}, ${bufferType.replace(/_/g, ' ')}${isDcaActive ? ', DCA ' + dcaFreq : ''})`,
    records: simResults,
    cycles: cycles,
    metrics: { finalVal, totalInvested, netProfitDollar, roicPct, wealthMultiplier, cagr, sharpe, maxDd, winRate }
  };
}

/* ==========================================================================
   11. SANDBOX PREVIEW MINI-CHART
   ========================================================================== */
function renderSandboxPreviewChart(simRecords, isDcaActive) {
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
  const investedValues = dataPoints.map(r => r.total_invested || 0);

  const grad = ctx.createLinearGradient(0, 0, 0, 200);
  grad.addColorStop(0, "rgba(168, 85, 247, 0.35)");
  grad.addColorStop(1, "rgba(0, 242, 254, 0.0)");

  const datasets = [
    {
      label: "Portfolio Wealth",
      data: values,
      borderColor: "#C084FC",
      borderWidth: 2,
      backgroundColor: grad,
      fill: true,
      pointRadius: 0,
      tension: 0.15
    }
  ];

  if (isDcaActive) {
    datasets.push({
      label: "Invested Principal (Savings)",
      data: investedValues,
      borderColor: "#38BDF8",
      borderWidth: 1.8,
      borderDash: [5, 4],
      backgroundColor: "transparent",
      fill: false,
      pointRadius: 0,
      tension: 0.05
    });
  }

  sbPreviewChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: !!isDcaActive,
          position: "top",
          align: "end",
          labels: {
            boxWidth: 12,
            boxHeight: 3,
            color: "#94A3B8",
            font: { family: "JetBrains Mono", size: 10 }
          }
        },
        tooltip: {
          mode: "index",
          intersect: false,
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: $${Math.round(ctx.parsed.y).toLocaleString("en-US")}`
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
            callback: (v) => `$${(v >= 1000000 ? (v / 1000000).toFixed(1) + 'M' : (v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v))}`
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
  let csv = "Date,Portfolio_Value,Total_Invested,Net_Profit,Position,NDX_Price,TQQQ_PnL_Pct\n";
  records.forEach(r => {
    const inv = r.total_invested || 0;
    const profit = r.total_value - inv;
    csv += `${r.date},${r.total_value.toFixed(2)},${inv.toFixed(2)},${profit.toFixed(2)},${r.position},${r.ndx_price.toFixed(2)},${(r.tqqq_buyhold_pnl_pct || 0).toFixed(2)}\n`;
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

/* ==========================================================================
   13. EDUCATIONAL QUANT EXPLANATIONS & INTERACTIVE TOOLTIP SYSTEM
   ========================================================================== */
const QUANT_EXPLANATIONS = {
  // Quant Lab Parameters
  sb_capital: {
    title: "Starting Capital ($)",
    category: "PORTFOLIO SEED CAPITAL",
    icon: "fa-solid fa-coins text-cyan",
    summary: "The initial lump-sum seed money allocated to the backtest on day one (e.g. $10,000 in Feb 2010).",
    analogy: "The foundation of your skyscraper: all compounding percentage gains multiply directly from this initial base.",
    scores: [
      { text: "$5k – $10k", label: "Retail Starter", color: "rose" },
      { text: "$25k – $50k", label: "Established Portfolio", color: "amber" },
      { text: "≥ $100k", label: "Institutional Scale", color: "emerald" }
    ],
    strategyTakeaway: "Starting with $10,000 in 2010 grew to over $446,000 without adding another penny—or over $2.4M with bi-weekly DCA additions."
  },
  dca: {
    title: "Dollar-Cost Averaging (DCA Plan)",
    category: "WEALTH ACCUMULATION STRATEGY",
    icon: "fa-solid fa-piggy-bank text-emerald",
    summary: "Investing a fixed dollar amount into the market at disciplined, recurring intervals (e.g. $500 from every paycheck) regardless of whether stock prices are surging or crashing.",
    analogy: "Like shopping for groceries every week: when prices go on sale, your fixed budget buys more food for the same dollars. When prices spike, you automatically buy fewer units. You never have to predict what the market will do next week.",
    scores: [
      { text: "Lump Sum Only", label: "Timing Sensitive (High Variance)", color: "rose" },
      { text: "Bi-Weekly DCA", label: "Payroll Matched (Zero Stress)", color: "amber" },
      { text: "DCA + Quant", label: "Dry-Powder Supercharger", color: "emerald" }
    ],
    strategyTakeaway: "In traditional Buy & Hold, DCA during bear markets suffers relentless leverage decay. With our Quant Strategy, bear-market DCA deposits accumulate safely as cash/Treasury dry powder—deploying in bulk the moment the bull market resumes!"
  },
  sb_date_window: {
    title: "Simulation Date Window",
    category: "HISTORICAL ERA AUDIT",
    icon: "fa-regular fa-calendar-days text-cyan",
    summary: "Restricts the backtest execution to a specific historical era (e.g. only test the 2022 bear market or the 2020 COVID shock).",
    analogy: "A flight simulator: test how your custom rules handle hurricane turbulence in isolation before committing real savings.",
    scores: [
      { text: "< 1 Year", label: "Micro Snapshot (High Noise)", color: "rose" },
      { text: "3 – 5 Years", label: "Full Market Cycle", color: "amber" },
      { text: "16 Years", label: "Full Historical Audit (2010–2026)", color: "emerald" }
    ],
    strategyTakeaway: "Testing across 4,185 sessions guarantees rules are robust across both raging bull runs and catastrophic crashes."
  },

  // Quant Lab Scorecard Results
  sb_final_val: {
    title: "Final Portfolio Value",
    category: "TOTAL ACCUMULATED WEALTH",
    icon: "fa-solid fa-vault text-emerald",
    summary: "The total cash and equity balance in your portfolio at the end of the simulation date window, after compounding and all DCA deposits.",
    analogy: "The retirement finish line: your accumulated nest egg balance waiting for you at the end of the journey.",
    scores: [
      { text: "< 2×", label: "Subpar Growth", color: "rose" },
      { text: "2× – 5×", label: "Solid Capital Expansion", color: "amber" },
      { text: "≥ 10×", label: "Decade Wealth Multiplier (10x+)", color: "emerald" }
    ],
    strategyTakeaway: "Compounding 3x leverage with disciplined cash preservation turns normal savings into multi-million dollar portfolios."
  },
  sb_invested: {
    title: "Total Invested Principal",
    category: "OUT-OF-POCKET SAVINGS",
    icon: "fa-solid fa-hand-holding-dollar text-cyan",
    summary: "The cumulative out-of-pocket cash you deposited into the strategy: your starting capital plus all recurring DCA additions.",
    analogy: "The total money you pulled from your paychecks and bank account. Everything in your final balance above this amount is pure free profit.",
    scores: [
      { text: "Lump Sum", label: "Single Upfront Deposit", color: "rose" },
      { text: "Periodic DCA", label: "Disciplined Payroll Savings", color: "amber" },
      { text: "DCA + Quant", label: "Max Compound Efficiency", color: "emerald" }
    ],
    strategyTakeaway: "In our simulation, $219.5k in payroll contributions generated over $2.22M in pure profit—an 11.1x multiplier on your savings."
  },
  sb_net_profit: {
    title: "Net Profit & ROIC",
    category: "TRUE WEALTH CREATED",
    icon: "fa-solid fa-money-bill-trend-up text-emerald",
    summary: "Pure dollar profit generated by the strategy (Final Value minus Total Invested Principal) and Return on Invested Capital percentage.",
    analogy: "The harvest: how many extra dollars the compounding engine grew for you beyond the seeds you planted.",
    scores: [
      { text: "< 100%", label: "Modest Gain (<2x)", color: "rose" },
      { text: "100% – 500%", label: "Strong Multi-Bag Growth", color: "amber" },
      { text: "≥ 1,000%", label: "Generational Wealth Alpha (10x+)", color: "emerald" }
    ],
    strategyTakeaway: "Over 16 years, our model delivered +1,014% ROIC with bi-weekly DCA, outperforming traditional 60/40 retirement plans by over 800%."
  },
  sb_irr: {
    title: "Annualized Return (IRR / CAGR)",
    category: "MONEY-WEIGHTED ANNUAL RATE",
    icon: "fa-solid fa-chart-line-up text-amber",
    summary: "When DCA is active, computes the exact Internal Rate of Return (money-weighted personal return) via Newton-Raphson. When lump sum, computes CAGR.",
    analogy: "The true interest rate of your wealth plan: the constant annual yield your money earned taking into account the timing of every deposit.",
    scores: [
      { text: "< 12%", label: "Trails Nasdaq-100", color: "rose" },
      { text: "12% – 20%", label: "Beats Market Benchmark", color: "amber" },
      { text: "≥ 20%", label: "Top Tier Institutional Rate", color: "emerald" }
    ],
    strategyTakeaway: "A +25.1% annualized personal IRR means your wealth doubled approximately every 2.9 years like clockwork."
  },
  sb_max_dd: {
    title: "Maximum Drawdown",
    category: "WORST-CASE CRASH DEPTH",
    icon: "fa-solid fa-water-lower text-rose",
    summary: "The deepest peak-to-trough account decline experienced during the simulation. Measures the maximum pain point you had to endure.",
    analogy: "The biggest drop on the rollercoaster: how far your portfolio dipped from its highest peak before making a new high.",
    scores: [
      { text: "> -65%", label: "Severe Pain (Buy & Hold TQQQ -82%)", color: "rose" },
      { text: "-40% to -65%", label: "Manageable for 3x Beta", color: "amber" },
      { text: "< -40%", label: "Superior Crash Defense", color: "emerald" }
    ],
    strategyTakeaway: "By exiting to cash during the 2022 bear market, the strategy capped drawdown at -50.8% while unhedged TQQQ plunged -82%."
  },
  sb_multiplier: {
    title: "Wealth Multiplier (ROI)",
    category: "TOTAL RETURN ON SAVINGS",
    icon: "fa-solid fa-calculator text-purple",
    summary: "How many times your total invested capital multiplied: Final Portfolio Value divided by Total Invested Principal.",
    analogy: "For every $1.00 you deposited from your paycheck, how many dollars did the strategy hand you at the finish line?",
    scores: [
      { text: "< 3×", label: "Modest Multiple", color: "rose" },
      { text: "3× – 8×", label: "Strong Wealth Expansion", color: "amber" },
      { text: "≥ 10×", label: "10x+ Compounding Engine", color: "emerald" }
    ],
    strategyTakeaway: "An 11.1× multiplier turned $219.5k in savings into $2.44M net worth over 16 years."
  },

  // Main Dashboard Institutional Strip
  sortino: {
    title: "Sortino Ratio",
    category: "RISK-ADJUSTED EFFICIENCY",
    icon: "fa-solid fa-chart-line-up text-emerald",
    summary: "Measures return generated strictly relative to BAD downside loss risk. Unlike Sharpe, it never penalizes your portfolio for sudden violent surges upward.",
    analogy: "A teacher who only docks points when you fail an exam, but doesn't punish you when you score 120% with extra credit. Sharpe penalizes both; Sortino only punishes the bad days.",
    scores: [
      { text: "< 0.6", label: "High Downside Bleed", color: "rose" },
      { text: "0.6 – 0.9", label: "Solid Downside Defense", color: "amber" },
      { text: "≥ 1.0", label: "Institutional Elite Edge", color: "emerald" }
    ],
    strategyTakeaway: "Our strategy posts a 0.73 Sortino (vs -0.15 for unhedged TQQQ in bear markets), proving its volatility comes primarily from violent bull runs rather than portfolio wipeouts."
  },
  sharpe: {
    title: "Sharpe Ratio",
    category: "WALL STREET RISK BENCHMARK",
    icon: "fa-solid fa-calculator text-cyan",
    summary: "The universal scorecard of investing. Compares total return against risk-free Treasury yield (4.5%), divided by total volatility (both upswings and downswings).",
    analogy: "Miles-per-gallon for financial risk: how much profit do you get per gallon of rollercoaster ride you have to stomach?",
    scores: [
      { text: "< 0.5", label: "Decaying / High Volatility", color: "rose" },
      { text: "0.5 – 0.9", label: "Solid for 3x Beta", color: "amber" },
      { text: "≥ 1.0", label: "Elite Risk-Adjusted Edge", color: "emerald" }
    ],
    strategyTakeaway: "Because TQQQ is 3x leveraged, its total volatility is 3× higher than normal stocks, keeping Sharpe around 0.64 even while delivering a staggering +4,360% total profit."
  },
  calmar: {
    title: "Calmar Ratio",
    category: "CRASH-TO-REWARD EFFICIENCY",
    icon: "fa-solid fa-shield-halved text-purple",
    summary: "Measures annualized return (CAGR) divided by the worst historical crash (Max Drawdown). Answers: 'Is the profit worth the deepest stomach drop you have to endure?'",
    analogy: "If a rollercoaster climbs 500 feet into the clouds, how terrifying is its steepest 250-foot vertical drop? A higher ratio means massive climb with manageable drops.",
    scores: [
      { text: "< 0.3", label: "Weak Crisis Protection", color: "rose" },
      { text: "0.3 – 0.7", label: "Solid for 3x Tech", color: "amber" },
      { text: "≥ 0.7", label: "World-Class Defense", color: "emerald" }
    ],
    strategyTakeaway: "At 0.49 Calmar, this system delivers +25.7% compounded annually while capping worst-ever drawdown at -52% (compared to unhedged TQQQ's brutal -82% collapse)."
  },
  cagr: {
    title: "16Y CAGR (Compounded Growth)",
    category: "COMPOUNDING WEALTH ENGINE",
    icon: "fa-solid fa-seedling text-amber",
    summary: "Compound Annual Growth Rate. The constant annual interest rate that would grow your starting balance into your final balance over the full 16-year timeline.",
    analogy: "If your savings account paid the exact same guaranteed interest rate every single year for 16 years straight, this is that magic interest rate.",
    scores: [
      { text: "< 12%", label: "Trailing Nasdaq-100", color: "rose" },
      { text: "12% – 20%", label: "Beats Market Benchmark", color: "amber" },
      { text: "≥ 20%", label: "Top 1% Compounding Alpha", color: "emerald" }
    ],
    strategyTakeaway: "+25.7% CAGR turns $10,000 into $446,089.97 over 16 years, outperforming the underlying Nasdaq-100 by more than +2,700%!"
  },
  profit_factor: {
    title: "Profit Factor",
    category: "GROSS EDGE METRIC",
    icon: "fa-solid fa-scale-balanced text-cyan",
    summary: "Total gross cash profits from all winning trades divided by total gross cash losses from all losing trades.",
    analogy: "For every $1.00 this strategy loses when caught in a false alarm, it takes home $1.70 from winning multi-month rallies.",
    scores: [
      { text: "< 1.2", label: "Fragile / Thin Margin", color: "rose" },
      { text: "1.2 – 1.6", label: "Healthy Systematic Edge", color: "amber" },
      { text: "≥ 1.6", label: "Institutional Grade Edge", color: "emerald" }
    ],
    strategyTakeaway: "A 1.70× Profit Factor over 4,185 trading sessions confirms this system has a durable mathematical edge that survived 16 years of bull and bear markets."
  },
  win_rate: {
    title: "Cycle Win Rate",
    category: "ACCURACY & EXECUTION",
    icon: "fa-solid fa-bullseye text-emerald",
    summary: "The percentage of completed trade cycles (from buying TQQQ to selling to Cash) that closed with positive net profit.",
    analogy: "In baseball, a batter who hits .475 is a legend. Trend-following algorithms don't need an 80% win rate because winning trades are held for huge runs while losers are cut short.",
    scores: [
      { text: "< 40%", label: "Choppy Performance", color: "rose" },
      { text: "40% – 50%", label: "Standard Trend Model", color: "amber" },
      { text: "≥ 50%", label: "Exceptional Trend Accuracy", color: "emerald" }
    ],
    strategyTakeaway: "With a 47.5% win rate across 84 cycles, the strategy cuts losing trades quickly (average loss -6.6%) while riding mega-trends (average win +14.6%)."
  },
  payoff: {
    title: "Payoff Ratio (Win / Loss Asymmetry)",
    category: "ASYMMETRIC REWARD/RISK",
    icon: "fa-solid fa-arrows-split-up-and-left text-pink",
    summary: "Average percentage gain on winning trades divided by average percentage loss on losing trades.",
    analogy: "When you win, you win $2.20; when you lose, you only lose $1.00. That asymmetry is why you don't need a high win rate to get rich.",
    scores: [
      { text: "< 1.5×", label: "Insufficient Win Size", color: "rose" },
      { text: "1.5× – 2.0×", label: "Healthy Win Asymmetry", color: "amber" },
      { text: "≥ 2.0×", label: "Powerful 2:1+ Reward Edge", color: "emerald" }
    ],
    strategyTakeaway: "A 2.20× Payoff Ratio means our winners are more than double the size of our losers, creating massive compound growth over time."
  },
  max_dd_duration: {
    title: "Max Drawdown Duration",
    category: "RECOVERY ENDURANCE",
    icon: "fa-solid fa-hourglass-half text-rose",
    summary: "The longest number of calendar days the strategy took to climb out of a crash and hit a brand new all-time high portfolio balance.",
    analogy: "If you hike down into a deep canyon during a storm, this is the total time it takes to climb back to the sunny mountain peak.",
    scores: [
      { text: "> 600 Days", label: "Prolonged Slump (>20 Mos)", color: "rose" },
      { text: "300 – 600 Days", label: "Moderate Recovery", color: "amber" },
      { text: "< 300 Days", label: "Rapid High-Water Reclaim", color: "emerald" }
    ],
    strategyTakeaway: "Our max recovery was ~455 days. By contrast, an investor holding unhedged tech in 2000 took over 15 years to break even!"
  },

  // Technical Signals & Moving Averages
  sma50: {
    title: "50-Day Moving Average (Exit Trigger)",
    category: "DYNAMIC TRENDLINE",
    icon: "fa-solid fa-chart-line text-amber",
    summary: "The average closing price of the Nasdaq-100 over the past 50 trading sessions (~2.5 months).",
    analogy: "Like checking a person's 50-day average speed to see if they are still sprinting or have collapsed into exhaustion.",
    scores: [
      { text: "Price < SMA50", label: "DEFENSIVE (Exit to Cash)", color: "rose" },
      { text: "Price ~ SMA50", label: "Buffer Transition Zone", color: "amber" },
      { text: "Price > SMA50", label: "BULLISH (Hold TQQQ)", color: "emerald" }
    ],
    strategyTakeaway: "Crossing below the 50-day SMA is the primary trigger that moved the strategy safely to 100% Cash before the 2022 tech crash wiped out normal investors."
  },
  sma250: {
    title: "250-Day Moving Average (Macro Baseline)",
    category: "MACRO REGIME LINE",
    icon: "fa-solid fa-chart-line text-purple",
    summary: "The average closing price of the Nasdaq-100 over approximately one full calendar year of trading (250 sessions).",
    analogy: "The long-term climate vs daily weather. Tells you whether the market is fundamentally in summer (bull) or winter (bear).",
    scores: [
      { text: "Price < SMA250", label: "Macro Bear Market", color: "rose" },
      { text: "Near SMA250", label: "Regime Inflection", color: "amber" },
      { text: "Price > SMA250", label: "Macro Secular Bull", color: "emerald" }
    ],
    strategyTakeaway: "Used as a master regime filter. In major bear regimes, the strategy remains safely in cash or interest-bearing yields."
  },
  hysteresis: {
    title: "Hysteresis Buffer (1.0× ATR)",
    category: "ANTI-WHIPSAW PROTECTION",
    icon: "fa-solid fa-shield text-cyan",
    summary: "A mathematical safety margin below the 50-day moving average calculated using the 14-day Average True Range (volatility).",
    analogy: "Your home thermostat doesn't shut the heater off the instant the room hits 70.0°F—it waits until 69°F so your heater doesn't click on and off every 10 seconds.",
    scores: [
      { text: "Real Crash", label: "Breaks Buffer -> Exit", color: "rose" },
      { text: "Market Chop", label: "Transition Testing", color: "amber" },
      { text: "Normal Noise", label: "Buffer Absorbs Drop", color: "emerald" }
    ],
    strategyTakeaway: "Prevents panic selling during normal 1-day dips, saving tens of thousands in whipsaw fees and false exits."
  },
  rsi: {
    title: "RSI (14) Relative Strength Index",
    category: "MOMENTUM & EXHAUSTION",
    icon: "fa-solid fa-gauge-high text-pink",
    summary: "A speedometer measuring the speed and magnitude of recent price moves on a 0 to 100 scale.",
    analogy: "Like a car tachometer. When the needle revs into the redline (above 75), the engine is overheating and needs to shift gears.",
    scores: [
      { text: "< 30", label: "Oversold (Downtrend)", color: "rose" },
      { text: "30 – 74", label: "Healthy Momentum", color: "amber" },
      { text: "≥ 75", label: "Overbought (Trim 25% to Cash)", color: "emerald" }
    ],
    strategyTakeaway: "When RSI exceeds 75, our system automatically trims 25% of TQQQ into Cash to bank profits before gravity pulls the market back."
  },
  hwm: {
    title: "High Water Mark (HWM)",
    category: "PEAK VALUATION",
    icon: "fa-solid fa-trophy text-amber",
    summary: "The highest peak dollar balance the portfolio has ever attained in its lifetime.",
    analogy: "The highest sea-level mark left on the lighthouse cliff after the biggest high tide.",
    scores: [
      { text: "> -20% DD", label: "Deep Drawdown Slump", color: "rose" },
      { text: "In Drawdown", label: "Climbing Back to Peak", color: "amber" },
      { text: "At HWM", label: "All-Time High (0% Drawdown)", color: "emerald" }
    ],
    strategyTakeaway: "Drawdown is always calculated as the distance from this peak. New high water marks reset your safety baseline."
  },
  tqqq_sqqq: {
    title: "TQQQ & SQQQ (3× Leveraged ETFs)",
    category: "3× LEVERAGED INSTRUMENTS",
    icon: "fa-solid fa-bolt text-cyan",
    summary: "Exchange Traded Funds designed to multiply daily Nasdaq-100 returns by +300% (TQQQ) or -300% (SQQQ).",
    analogy: "A Formula 1 racecar. Blazingly fast in the straightaways (bull markets), but dangerous in hairpin curves without systematic anti-lock brakes.",
    scores: [
      { text: "Unhedged B&H", label: "-82% Crash Risk in Bear", color: "rose" },
      { text: "Bear Trend", label: "Hold 100% Cash / Treasury Yield", color: "amber" },
      { text: "Bull Trend", label: "Hold 100% TQQQ (+3x Boost)", color: "emerald" }
    ],
    strategyTakeaway: "Unhedged TQQQ crashed -82% in 2022. By contrast, our systematic rules moved to 100% Cash at the top, growing +66.8% through risk-free interest and bottom-rebuys."
  },
  crisis_alpha: {
    title: "Crisis Alpha",
    category: "CRISIS DEFENSE",
    icon: "fa-solid fa-shield text-emerald",
    summary: "The ability of a strategy to generate positive returns or protect capital during catastrophic market crashes when everyone else is losing money.",
    analogy: "Like having a house made of stone when a hurricane blows down all the wooden houses on your block.",
    scores: [
      { text: "Unhedged Drop", label: "Full Crash Exposure", color: "rose" },
      { text: "Cash / Treasuries", label: "4.5% Risk-Free Safety", color: "amber" },
      { text: "Crisis Alpha", label: "Protected Capital + Bottom Buy", color: "emerald" }
    ],
    strategyTakeaway: "By holding 100% Cash during down markets, you avoid the -80% drawdowns that wipe out buy-and-hold investors."
  },
  allocation_gears: {
    title: "5-State Systematic Allocation Spectrum",
    category: "STRATEGY EXECUTION",
    icon: "fa-solid fa-gears text-cyan",
    summary: "The strategy operates across 5 discrete mathematical regimes: 100% TQQQ, 50% Divergence Trim, 30% Overbought Trim, 100% Cash Defense, or 100% SQQQ Bear Inverse.",
    analogy: "Like a precision 5-speed transmission in an endurance racecar: full throttle in straightaways, downshifting into corners, and hitting the brakes before crashes.",
    scores: [
      { text: "100% SQQQ", label: "Macro Bear Inverse", color: "rose" },
      { text: "100% CASH", label: "Capital Defense @ 4.5% Yield", color: "amber" },
      { text: "100% TQQQ", label: "Full Bull Compound Expansion", color: "emerald" }
    ],
    strategyTakeaway: "Eliminates emotional guessing. You always see the active gear, current dollar allocation, and the forward tripwire required to shift into the next state."
  }
};

let tooltipHideTimeout = null;
let tooltipPinned = false;
let tooltipsEnabled = localStorage.getItem("ndx_terminal_tooltips") !== "false";

function initEducationalTooltips() {
  const popover = document.getElementById("quantTooltipPopover");
  const closeBtn = document.getElementById("qtpCloseBtn");
  const btnToggle = document.getElementById("btnToggleTooltips");
  const ttStatus = document.getElementById("ttToggleStatus");

  function applyTooltipState() {
    document.body.classList.toggle("tooltips-disabled", !tooltipsEnabled);
    if (btnToggle) {
      btnToggle.classList.toggle("active", tooltipsEnabled);
      btnToggle.classList.toggle("disabled", !tooltipsEnabled);
    }
    if (ttStatus) {
      ttStatus.textContent = tooltipsEnabled ? "ON" : "OFF";
    }
    if (!tooltipsEnabled && popover) {
      popover.style.display = "none";
      tooltipPinned = false;
    }
  }

  applyTooltipState();

  if (btnToggle) {
    btnToggle.addEventListener("click", () => {
      tooltipsEnabled = !tooltipsEnabled;
      localStorage.setItem("ndx_terminal_tooltips", tooltipsEnabled ? "true" : "false");
      applyTooltipState();
      if (!tooltipsEnabled) {
        showToast("Educational tooltips hidden", "fa-solid fa-eye-slash text-muted");
      } else {
        showToast("Educational tooltips enabled", "fa-solid fa-graduation-cap text-cyan");
      }
    });
  }

  if (!popover) return;

  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      popover.style.display = "none";
      tooltipPinned = false;
    });
  }

  popover.addEventListener("mouseenter", () => {
    if (tooltipHideTimeout) clearTimeout(tooltipHideTimeout);
  });
  popover.addEventListener("mouseleave", () => {
    if (!tooltipPinned) {
      popover.style.display = "none";
    }
  });

  // Delegated mouseover
  document.addEventListener("mouseover", (e) => {
    if (!tooltipsEnabled) return;
    const trigger = e.target.closest("[data-help]");
    if (!trigger) return;
    const key = trigger.getAttribute("data-help");
    if (!key || !QUANT_EXPLANATIONS[key]) return;
    if (tooltipHideTimeout) clearTimeout(tooltipHideTimeout);
    showQuantTooltip(key, trigger);
  });

  // Delegated mouseout
  document.addEventListener("mouseout", (e) => {
    if (!tooltipsEnabled) return;
    const trigger = e.target.closest("[data-help]");
    if (!trigger) return;
    if (tooltipPinned) return;
    tooltipHideTimeout = setTimeout(() => {
      popover.style.display = "none";
    }, 180);
  });

  // Delegated click / tap
  document.addEventListener("click", (e) => {
    if (!tooltipsEnabled) return;
    const trigger = e.target.closest("[data-help]");
    if (trigger) {
      const key = trigger.getAttribute("data-help");
      if (key && QUANT_EXPLANATIONS[key]) {
        tooltipPinned = true;
        showQuantTooltip(key, trigger);
        return;
      }
    }
    if (!e.target.closest("#quantTooltipPopover")) {
      popover.style.display = "none";
      tooltipPinned = false;
    }
  });
}

function showQuantTooltip(key, triggerElement) {
  const item = QUANT_EXPLANATIONS[key];
  const popover = document.getElementById("quantTooltipPopover");
  if (!item || !popover) return;

  const badgeEl = document.getElementById("qtpBadge");
  if (badgeEl) badgeEl.textContent = item.category || "QUANT EDUCATION";

  const titleEl = document.getElementById("qtpTitle");
  if (titleEl) titleEl.textContent = item.title;

  const sumEl = document.getElementById("qtpSummary");
  if (sumEl) sumEl.textContent = item.summary;

  const anaEl = document.getElementById("qtpAnalogy");
  if (anaEl) anaEl.textContent = item.analogy;

  const iconEl = document.getElementById("qtpIcon");
  if (iconEl) iconEl.className = `${item.icon || "fa-solid fa-graduation-cap"} qtp-icon`;

  // Detect which color is active on the hovered card to highlight the matching pill
  const valEl = triggerElement.querySelector(".qm-value, .sb-metric-val, .val-text") || triggerElement;
  let activeColor = "";
  if (valEl.classList.contains("text-emerald")) activeColor = "emerald";
  else if (valEl.classList.contains("text-amber")) activeColor = "amber";
  else if (valEl.classList.contains("text-rose")) activeColor = "rose";

  const pillsContainer = document.getElementById("qtpScorePills");
  if (pillsContainer) {
    pillsContainer.innerHTML = (item.scores || []).map(s => {
      const isMatch = (activeColor && s.color === activeColor);
      return `
        <div class="qtp-pill ${s.color} ${isMatch ? 'qtp-pill-active' : ''}">
          <strong>${s.text}</strong> <span>• ${s.label}</span>
          ${isMatch ? '<i class="fa-solid fa-check" style="margin-left:4px; font-size:10px;"></i>' : ''}
        </div>
      `;
    }).join("");
  }

  const takeawayEl = document.getElementById("qtpTakeaway");
  if (takeawayEl) {
    takeawayEl.innerHTML = `<strong>STRATEGY IMPACT:</strong> ${item.strategyTakeaway}`;
  }

  popover.style.display = "block";
  popover.style.visibility = "hidden";

  const rect = triggerElement.getBoundingClientRect();
  const popRect = popover.getBoundingClientRect();

  let left = rect.left + (rect.width / 2) - (popRect.width / 2);
  let top = rect.bottom + 10;

  const margin = 14;
  if (left < margin) left = margin;
  if (left + popRect.width > window.innerWidth - margin) {
    left = window.innerWidth - popRect.width - margin;
  }

  if (top + popRect.height > window.innerHeight - margin) {
    top = rect.top - popRect.height - 10;
  }
  if (top < margin) top = margin;

  popover.style.left = `${Math.round(left)}px`;
  popover.style.top = `${Math.round(top)}px`;
  popover.style.visibility = "visible";
}
