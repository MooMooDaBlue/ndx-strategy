/**
 * NDX Quantitative Strategy — Client-Side Application
 * Provides real-time telemetry, Chart.js visualizations, interactive capital simulation,
 * multi-era stress testing, and terminal streaming.
 */

let currentTab = "equity";
let currentTimeframe = "ALL";
let simulatedCapital = 10000;
let cachedData = null;
let chartInstance = null;
let autoRefreshTimer = null;

// Clock and countdown timers
setInterval(updateClocks, 1000);

document.addEventListener("DOMContentLoaded", () => {
  initEventListeners();
  fetchDashboardData();
  startAutoRefresh();
});

function initEventListeners() {
  // Tabs switching
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentTab = btn.getAttribute("data-tab");
      renderChart();
    });
  });

  // Timeframe buttons
  document.querySelectorAll(".tf-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tf-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentTimeframe = btn.getAttribute("data-tf");
      renderChart();
    });
  });

  // Capital Simulator Preset Buttons
  document.querySelectorAll(".sim-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".sim-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      simulatedCapital = parseFloat(btn.getAttribute("data-amt")) || 10000;
      const customInput = document.getElementById("simCustomCapital");
      if (customInput) customInput.value = simulatedCapital;
      if (cachedData) {
        renderUI(cachedData);
        renderChart();
      }
    });
  });

  // Capital Simulator Custom Input
  const customInput = document.getElementById("simCustomCapital");
  if (customInput) {
    customInput.addEventListener("input", (e) => {
      const val = parseFloat(e.target.value);
      if (!isNaN(val) && val > 0) {
        simulatedCapital = val;
        document.querySelectorAll(".sim-btn").forEach(b => {
          if (parseFloat(b.getAttribute("data-amt")) === val) {
            b.classList.add("active");
          } else {
            b.classList.remove("active");
          }
        });
        if (cachedData) {
          renderUI(cachedData);
          renderChart();
        }
      }
    });
  }

  // Manual Sync Button
  const btnRefresh = document.getElementById("btnRefresh");
  if (btnRefresh) {
    btnRefresh.addEventListener("click", () => {
      const icon = document.getElementById("refreshIcon");
      if (icon) icon.classList.add("fa-spin");
      fetchDashboardData().finally(() => {
        if (icon) setTimeout(() => icon.classList.remove("fa-spin"), 600);
      });
    });
  }

  // Run Strategy Now Button
  const btnRun = document.getElementById("btnRunStrategy");
  if (btnRun) {
    btnRun.addEventListener("click", async () => {
      const isLocal = window.location.port === "5050" || window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
      if (!isLocal) {
        if (confirm("You are viewing the hosted cloud dashboard on GitHub Pages.\n\nStrategy runs automatically every trading day at 1:50 PM MT via GitHub Actions.\n\nWould you like to open GitHub Actions to trigger an instant cloud run now?")) {
          window.open("https://github.com/MooMooDaBlue/ndx-strategy/actions", "_blank");
        }
        return;
      }

      if (!confirm("Execute trading strategy check now?")) return;
      btnRun.disabled = true;
      btnRun.classList.add("running");
      const runText = document.getElementById("runText");
      const originalText = runText ? runText.textContent : "Run Now";
      if (runText) runText.textContent = "Executing...";
      try {
        const res = await fetch("/api/run_strategy", { method: "POST" });
        const result = await res.json();
        if (result.status === "success") {
          alert("Strategy run complete! Data refreshed.");
        } else if (result.status === "skipped") {
          alert("Run skipped: " + result.message);
        } else {
          alert("Status: " + (result.message || result.status));
        }
        await fetchDashboardData();
      } catch (err) {
        alert("Failed to execute strategy: " + err.message);
      } finally {
        btnRun.disabled = false;
        btnRun.classList.remove("running");
        if (runText) runText.textContent = originalText;
      }
    });
  }

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
    const endpoint = isLocal ? "/api/data" : "./data.json";
    const res = await fetch(endpoint + "?_t=" + Date.now());
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
   UI RENDERING
   ========================================================================== */
function renderUI(data) {
  const p = data.portfolio;
  const stats = data.stats;
  const cfg = data.config;
  const daily = data.daily_summary;

  const baseStartCap = p.starting_capital || 10000;
  const scaleFactor = simulatedCapital / baseStartCap;

  // 1. Header Market Status & Clock
  updateMarketStatus();

  // 2. Regime Banner
  const isProtected = p.position.includes("TQQQ");
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
  document.getElementById("ndxLevel").textContent = stats.ndx_price.toLocaleString("en-US", { minimumFractionDigits: 2 });
  document.getElementById("ndxSma50").textContent = `SMA50: ${stats.sma50.toLocaleString("en-US", { minimumFractionDigits: 1 })}`;
  document.getElementById("ndxSma250").textContent = `SMA250: ${stats.sma250.toLocaleString("en-US", { minimumFractionDigits: 1 })}`;
  document.getElementById("rsiValue").textContent = stats.rsi.toFixed(1);

  const rsiBadge = document.getElementById("rsiZoneBadge");
  if (stats.rsi >= 75) {
    rsiBadge.textContent = "OVERBOUGHT";
    rsiBadge.style.color = "#F43F5E";
    rsiBadge.style.background = "rgba(244, 63, 94, 0.15)";
  } else if (stats.rsi <= 30) {
    rsiBadge.textContent = "OVERSOLD";
    rsiBadge.style.color = "#00F2FE";
    rsiBadge.style.background = "rgba(0, 242, 254, 0.15)";
  } else {
    rsiBadge.textContent = "NEUTRAL";
    rsiBadge.style.color = "#00E676";
    rsiBadge.style.background = "rgba(0, 230, 118, 0.15)";
  }

  // Populate Year Filter if not already populated
  const yearSelect = document.getElementById("tradeYearFilter");
  if (yearSelect && yearSelect.options.length <= 1 && data.trades) {
    const years = [...new Set(data.trades.map(t => (t.date || "").substring(0, 4)).filter(Boolean))].sort().reverse();
    years.forEach(yr => {
      const opt = document.createElement("option");
      opt.value = yr;
      opt.textContent = yr;
      yearSelect.appendChild(opt);
    });
  }

  // 4. Telemetry Panel
  const telemetryPos = document.getElementById("telemetryPos");
  if (telemetryPos) telemetryPos.textContent = p.position;
  const telemetrySignal = document.getElementById("telemetrySignal");
  if (telemetrySignal) telemetrySignal.textContent = p.last_signal || "HOLD";
  const statTrades = document.getElementById("statTotalTrades");
  if (statTrades) statTrades.textContent = stats.total_trades;
  const statDays = document.getElementById("statDaysTracked");
  if (statDays) statDays.textContent = `${stats.trading_days_tracked} days`;
  const statDD = document.getElementById("statMaxDD");
  if (statDD) statDD.textContent = `${stats.max_drawdown_pct.toFixed(2)}%`;
  const statHWM = document.getElementById("statHWM");
  if (statHWM) statHWM.textContent = formatCurrency(stats.high_water_mark * scaleFactor);

  // 5. Trades Table
  renderTradesTable(data.trades);

  // 6. Strategy Log Terminal
  renderTerminal(data.recent_logs);
}

/* ==========================================================================
   CHART RENDERING (CHART.JS)
   ========================================================================== */
function renderChart() {
  if (!cachedData || !cachedData.daily_summary) return;

  const ctx = document.getElementById("mainChart").getContext("2d");
  let records = [...cachedData.daily_summary];

  // Apply Timeframe & Era Filters
  if (currentTimeframe === "1M") {
    records = records.slice(-22);
  } else if (currentTimeframe === "6M") {
    records = records.slice(-126);
  } else if (currentTimeframe === "1Y") {
    records = records.slice(-252);
  } else if (currentTimeframe === "5Y") {
    records = records.filter(r => r.date >= "2021-01-01");
  } else if (currentTimeframe === "2022") {
    records = records.filter(r => r.date >= "2022-01-01" && r.date <= "2022-12-31");
  } else if (currentTimeframe === "2020") {
    records = records.filter(r => r.date >= "2020-01-01" && r.date <= "2020-12-31");
  }

  // Sampling for silky smooth performance on multi-thousand point datasets
  let plotRecords = records;
  if (plotRecords.length > 500) {
    const step = Math.ceil(plotRecords.length / 400);
    const sampled = [];
    for (let i = 0; i < plotRecords.length; i += step) {
      sampled.push(plotRecords[i]);
    }
    if (sampled[sampled.length - 1] !== plotRecords[plotRecords.length - 1]) {
      sampled.push(plotRecords[plotRecords.length - 1]);
    }
    plotRecords = sampled;
  }

  const labels = plotRecords.map(r => r.date);
  const legendBox = document.getElementById("chartLegend");

  if (chartInstance) {
    chartInstance.destroy();
  }

  const baseStartCap = cachedData.portfolio.starting_capital || 10000;
  const scaleFactor = simulatedCapital / baseStartCap;

  if (currentTab === "equity") {
    // --- TAB 1: EQUITY VS BENCHMARKS (REBASED TO TIMEFRAME START) ---
    const r0 = plotRecords[0];
    const rEnd = plotRecords[plotRecords.length - 1];

    const stratStartVal = Math.max(0.0001, r0.total_value);
    const ndxStartRatio = Math.max(0.0001, 1 + (r0.ndx_buyhold_pnl_pct || 0) / 100);
    const tqqqStartRatio = Math.max(0.0001, 1 + (r0.tqqq_buyhold_pnl_pct || 0) / 100);

    // Rebased to simulatedCapital at the start of this specific timeframe
    const equityData = plotRecords.map(r => simulatedCapital * (r.total_value / stratStartVal));
    const baseLine = plotRecords.map(() => simulatedCapital);
    const ndxNorm = plotRecords.map(r => simulatedCapital * ((1 + (r.ndx_buyhold_pnl_pct || 0) / 100) / ndxStartRatio));
    const tqqqNorm = plotRecords.map(r => simulatedCapital * ((1 + (r.tqqq_buyhold_pnl_pct || 0) / 100) / tqqqStartRatio));

    const stratEndVal = equityData[equityData.length - 1];
    const ndxEndVal = ndxNorm[ndxNorm.length - 1];
    const tqqqEndVal = tqqqNorm[tqqqNorm.length - 1];

    const stratRet = ((stratEndVal / simulatedCapital) - 1) * 100;
    const ndxRet = ((ndxEndVal / simulatedCapital) - 1) * 100;
    const tqqqRet = ((tqqqEndVal / simulatedCapital) - 1) * 100;

    const stratSign = stratRet >= 0 ? "+" : "";
    const ndxSign = ndxRet >= 0 ? "+" : "";
    const tqqqSign = tqqqRet >= 0 ? "+" : "";

    const gradCyan = ctx.createLinearGradient(0, 0, 0, 350);
    gradCyan.addColorStop(0, "rgba(0, 242, 254, 0.28)");
    gradCyan.addColorStop(1, "rgba(0, 242, 254, 0.0)");

    chartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Strategy Portfolio",
            data: equityData,
            borderColor: "#00F2FE",
            borderWidth: 2.5,
            backgroundColor: gradCyan,
            fill: true,
            tension: 0.2,
            pointRadius: plotRecords.length > 60 ? 0 : 3,
            pointHoverRadius: 6,
          },
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
        ]
      },
      options: getCommonChartOptions("$")
    });

    legendBox.innerHTML = `
      <div class="legend-item"><span class="legend-color-box" style="background:#00F2FE;"></span> Strategy: <strong>${formatCurrency(stratEndVal)}</strong> (${stratSign}${stratRet.toFixed(2)}%)</div>
      <div class="legend-item"><span class="legend-color-box" style="background:#A855F7;"></span> NDX: <strong>${formatCurrency(ndxEndVal)}</strong> (${ndxSign}${ndxRet.toFixed(2)}%)</div>
      <div class="legend-item"><span class="legend-color-box" style="background:#F59E0B;"></span> TQQQ: <strong>${formatCurrency(tqqqEndVal)}</strong> (${tqqqSign}${tqqqRet.toFixed(2)}%)</div>
      <div class="legend-item"><span class="legend-color-box" style="background:rgba(255,255,255,0.4); border: 1px dashed white;"></span> Baseline: <strong>${formatCurrency(simulatedCapital)}</strong></div>
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
            return value.toLocaleString();
          }
        }
      }
    }
  };
}

/* ==========================================================================
   TRADES TABLE RENDERING & FILTERING
   ========================================================================== */
function renderTradesTable(trades) {
  applyTradeFilters();
}

function applyTradeFilters() {
  if (!cachedData || !cachedData.trades) return;

  const actionFilter = document.getElementById("tradeActionFilter");
  const yearFilter = document.getElementById("tradeYearFilter");
  const searchInput = document.getElementById("tradeSearchInput");

  const actionVal = actionFilter ? actionFilter.value : "ALL";
  const yearVal = yearFilter ? yearFilter.value : "ALL";
  const query = searchInput ? searchInput.value.toLowerCase().trim() : "";

  const baseStartCap = cachedData.portfolio.starting_capital || 10000;
  const scaleFactor = simulatedCapital / baseStartCap;

  let filtered = [...cachedData.trades];

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

  const tbody = document.getElementById("tradeTableBody");
  if (!filtered || filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">No trades match selected filters.</td></tr>`;
    return;
  }

  // Reverse so newest trades appear on top
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
        <td><strong>$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong></td>
        <td>${ndx.toLocaleString("en-US", { minimumFractionDigits: 1 })}</td>
        <td><span class="trade-reason-text" title="${t.reason}">${t.reason}</span></td>
      </tr>
    `;
  }).join("");
}

/* ==========================================================================
   TERMINAL LOG RENDERING
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
   TIME & MARKET STATUS HELPERS
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
