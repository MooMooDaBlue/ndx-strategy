# NDX Quant Systematic Trading Strategy & Terminal

[![Daily Strategy Execution & Pages Sync](https://github.com/MooMooDaBlue/ndx-strategy/actions/workflows/daily_strategy.yml/badge.svg)](https://github.com/MooMooDaBlue/ndx-strategy/actions/workflows/daily_strategy.yml)
[![Live Web Dashboard](https://img.shields.io/badge/Live_Dashboard-GitHub_Pages-00E676?style=flat&logo=googlechrome&logoColor=white)](https://MooMooDaBlue.github.io/ndx-strategy/)

> [!CAUTION]
> # ⚠️ DISCLAIMER: THIS IS NOT FINANCIAL ADVICE ⚠️
> **THIS PROJECT IS STRICTLY AN OPEN-SOURCE PAPER-TRADING SIMULATOR AND QUANTITATIVE BENCHMARK FOR RESEARCH AND EDUCATIONAL PURPOSES ONLY.**
>
> - **DO NOT TRADE REAL MONEY BASED ON THIS SYSTEM, REPOSITORY, DATA, OR SIGNALS.**
> - Leveraged instruments like **TQQQ (3x Bull)** and **SQQQ (3x Bear)** carry severe volatility decay and high risk of **total loss of capital**.
> - Simulated, hypothetical, or backtested performance is **never a guarantee of future market results**.
> - The developers and contributors assume **no responsibility or liability** for any financial trades or investment decisions you make.

A fully automated paper-trading strategy and monitoring dashboard for NASDAQ-100 leveraged ETFs (**TQQQ / SQQQ**).

Runs serverless in the cloud via GitHub Actions and GitHub Pages; no local hardware is required.

---

## 🌐 Live Cloud Dashboard

The live interactive terminal is hosted continuously on GitHub Pages:

👉 **[https://MooMooDaBlue.github.io/ndx-strategy/](https://MooMooDaBlue.github.io/ndx-strategy/)**

- **Dual Strategy Ruleset Benchmarking**: Toggle between **Symmetric 1.0× ATR** (ATR hysteresis around SMA50) and **Original Agile Model** (SMA50 stop & 1% re-entry buffer), or overlay both on the chart. Return badges are computed from the data, not hard-coded.
- **Interactive Capital Simulator**: Test any initial capital amount ($5K, $10K, $25K, $50K, $100K presets or any custom figure) to see scaled returns, drawdowns, and compounded terminal value.
- **Multi-Era Macro Stress-Testing**: Instant 1-click toggles across key historical regimes: **1M**, **6M**, **1Y**, **5Y**, **2022 Bear Market** (-80% TQQQ crash avoidance), **2020 COVID Crash**, and **16Y Full Inception (2010–2026)**.
- **Market Tracking**: NDX status and indicator gauges (SMA50, SMA250, RSI-14). The Top-20 heatmap is live on the local dashboard and a once-a-day snapshot on Pages.
- **Interactive Multi-Chart Studio**: Dynamic Chart.js visualizations for Strategy vs Buy-and-Hold benchmarks, NDX vs SMA trend bands, and RSI momentum zones.
- **Searchable Execution Ledger**: Every executed leg (BUY / SELL / TRIM) with fill price and slippage cost, with year filter.
- **Streaming Execution Terminal**: Monospaced terminal display streaming real-time strategy logs.

---

## 📊 Backtest Results (2010-02-11 → 2026-10-16, $10,000 start)

| Model | Total return | CAGR | Max drawdown |
|---|---|---|---|
| Symmetric 1.0× ATR | +1,826% | 19.4% | −52.6% |
| Original Agile | +1,400% | 17.6% | −61.2% |
| NDX buy & hold | +1,544% | — | — |
| TQQQ buy & hold | +33,143% | — | — |

Includes 5 bps slippage per leg and T-bill interest on cash. See **Methodology & limitations** before reading anything into these numbers.

---

## ⚡ Cloud Automation Architecture

```
                       ┌────────────────────────────────────────┐
                       │  GitHub Actions Cron (Mon-Fri, several │
                       │  attempts after the 4:00 PM ET close)  │
                       └───────────────────┬────────────────────┘
                                           │
                                           ▼
                       ┌────────────────────────────────────────┐
                       │   Execute: run_cloud_strategy.py       │
                       │   • Fetch ^NDX, TQQQ, SQQQ, ^IRX        │
                       │   • Evaluate Symmetric 1.0x ATR Signal │
                       │   • Update portfolio_state.json        │
                       │   • Send ntfy.sh Mobile Alert          │
                       └───────────────────┬────────────────────┘
                                           │
                                           ▼
                       ┌────────────────────────────────────────┐
                       │   Auto-Commit & GitHub Pages Deploy    │
                       │   • Export docs/data.json payload      │
                       │   • Render performance_chart.png       │
                       │   • Push to main with [skip ci]        │
                       └───────────────────┬────────────────────┘
                                           │
                                           ▼
                       ┌────────────────────────────────────────┐
                       │  GitHub Pages dashboard (docs/)        │
                       │  https://MooMooDaBlue.github.io/       │
                       │  ndx-strategy/                         │
                       └────────────────────────────────────────┘
```

- **Daily Auto-Run**: Executes Monday–Friday after the 4:00 PM ET close (window 16:00–23:59 ET; GitHub cron is often late, so several attempts are scheduled and only the first one runs).
- **NYSE Holiday Protection**: Automatically checks NYSE trading holiday calendars (Good Friday, Memorial Day, Labor Day, etc.) and skips closed sessions.
- **On-Demand Cloud Runs**: Can be triggered anytime via the **Actions** tab on GitHub using `workflow_dispatch`.
- **Phone Notifications**: Dispatches real-time markdown notifications with trade decisions to your phone via `ntfy.sh`.

---

## 🛡️ Core Strategy & Downside Protection Rules

1. **Regime Filter (SMA250)**:
   - NDX > SMA250: Bull regime (TQQQ long exposure permitted).
   - NDX < SMA250: Bear regime (defensive cash or tactical SQQQ short exposure).

2. **Symmetric 1.0× ATR Hysteresis & Downside Protection**:
   - **Re-Entry Buffer**: When in Cash, price must clear `SMA50 + (1.0 × ATR)` to confirm re-entry and avoid buying false bounces.
   - **Downside Protection Floor**: When holding TQQQ, shallow dips below the 50-day SMA do **not** trigger exits, in either regime. Price must close below `SMA50 - (1.0 × ATR)` (Wilder ATR-14) to exit.

3. **Momentum & Divergence Management**:
   - **Overbought Trim**: RSI-14 $\ge 75$ trims allocation to 30% TQQQ with momentum reset lock.
   - **Bearish Divergence**: Trims allocation to 50% TQQQ when higher price highs coincide with lower RSI highs.
   - **Tactical Shorting**: In deep bear regimes (below both SMAs), enters SQQQ only within the RSI 35–55 sweet spot, avoiding oversold short traps.

---

## 🔬 Methodology & limitations

- **Execution model**: signals use the official daily close and fill at that same close (a market-on-close assumption) with 5 bps slippage per leg. No commissions, borrow costs or taxes; fractional shares are allowed.
- **Backtest vs. live**: history up to `backtest_end` (in `portfolio_state.json`) is simulated (`source=backtest` rows); rows written by the daily cloud run are `source=live`. The "live" equity curve continues from the simulated portfolio — it is not an independent track record.
- **Overfitting**: thresholds (ATR multiple, RSI levels, buffers) were chosen with knowledge of this same 2010–2026 history. Expect out-of-sample results to be worse.
- **Corporate actions**: live runs adjust held shares for splits and credit cash dividends; the backtest uses total-return-adjusted prices.
- **Heatmap weights** are static approximations (see `TOP_20_AS_OF` in `web_dashboard.py`).

## 📁 Files

| File | Contents |
|---|---|
| `portfolio_state.json`, `daily_summary.csv`, `trade_log.csv` | Symmetric ATR model (primary) |
| `portfolio_state_agile.json`, `daily_summary_agile.csv`, `trade_log_agile.csv` | Original Agile model |
| `docs/` | The only frontend copy — served by GitHub Pages and by the local dashboard |
| `generate_full_16y_data.py` | Regenerates both models' full history with the live engine |

---

## 💻 Optional Local Running

You can also run everything locally on your PC whenever you wish:

```bash
# 1-Click Windows Launcher:
run_dashboard.bat

# Or via Command Line:
python web_dashboard.py
```
*(Runs the local view-only web server at `http://127.0.0.1:5050` and warns if your checkout is behind the cloud's commits).*

Tests are offline: `python -m pytest -q tests`.

---

## ⚠️ Comprehensive Legal Disclaimer — THIS IS NOT FINANCIAL ADVICE

> **READ CAREFULLY BEFORE ACCESSING, USING, OR FORKING THIS REPOSITORY:**
>
> 1. **NOT FINANCIAL, LEGAL, OR INVESTMENT ADVICE**: None of the content, code, algorithms, data, backtests, simulations, charts, trade logs, or signals presented in this repository or associated web dashboards constitute financial, investment, legal, tax, or trading advice. It is strictly not an offer, recommendation, or solicitation to buy or sell any security, ETF, derivative, or digital asset.
> 2. **EDUCATIONAL & PAPER-TRADING BENCHMARK ONLY**: This software is an open-source paper-trading framework and quantitative simulation designed purely to benchmark algorithmic models against buy-and-hold strategies. Simulated paper trades do not represent actual trading and have fundamental limitations (e.g. liquidity constraints, transaction fees, execution delays, margin/borrow rates, and psychological factors are not modeled). Cash earns 13-week T-bill yields; slippage is a flat 5 bps per leg; no fees or taxes are modeled.
> 3. **EXTREME LEVERAGED ETF RISKS**: Triple-leveraged ETFs (**TQQQ** and **SQQQ**) are high-risk financial derivatives designed solely for short-term institutional speculation. Holding leveraged ETFs over extended periods carries extreme compounding risk, volatility decay, and substantial probability of catastrophic loss or total depletion of invested capital.
> 4. **NO WARRANTY & ZERO LIABILITY**: The software is provided "as is", without warranty of any kind, express or implied. The author, maintainers, and contributors are not licensed financial advisors, broker-dealers, or registered analysts. Under no circumstances shall the author or contributors be liable for any direct, indirect, special, incidental, or consequential damages or financial losses arising from the use of or inability to use this repository. Always consult an accredited financial professional before making real investment decisions.
