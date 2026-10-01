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

An institutional-grade, fully automated algorithmic paper-trading strategy and real-time monitoring terminal for NASDAQ-100 leveraged ETFs (**TQQQ / SQQQ**). 

Runs **100% serverless and autonomously** in the cloud via GitHub Actions and GitHub Pages with zero required local hardware or maintenance.

---

## 🌐 Live Cloud Dashboard

The live interactive terminal is hosted continuously on GitHub Pages:

👉 **[https://MooMooDaBlue.github.io/ndx-strategy/](https://MooMooDaBlue.github.io/ndx-strategy/)**

- **Dual Strategy Ruleset Benchmarking**: Toggle between **Symmetric 1.0× ATR** (Macro Defensive Hysteresis, +4,361% 16Y return) and **Original Agile Model** (Fast SMA50 Stop & 1% Confirmation Buffer, +2,976% 16Y return), or overlay both models side-by-side on the chart!
- **Interactive Capital Simulator**: Test any initial capital amount ($5K, $10K, $25K, $50K, $100K presets or any custom figure) to see scaled returns, drawdowns, and compounded terminal value.
- **Multi-Era Macro Stress-Testing**: Instant 1-click toggles across key historical regimes: **1M**, **6M**, **1Y**, **5Y**, **2022 Bear Market** (-80% TQQQ crash avoidance), **2020 COVID Crash**, and **16Y Full Inception (2010–2026)**.
- **Real-Time Market Tracking**: Live NDX status, countdown timer to daily run, and key indicator gauges (SMA50, SMA250, RSI-14).
- **Interactive Multi-Chart Studio**: Dynamic Chart.js visualizations for Strategy vs Buy-and-Hold benchmarks, NDX vs SMA trend bands, and RSI momentum zones.
- **Searchable Execution Ledger**: Audited table of all 460+ historical trades with action filter (BUY/SELL/TRIM) and year filter (2010–2026).
- **Streaming Execution Terminal**: Monospaced terminal display streaming real-time strategy logs.

---

## ⚡ Cloud Automation Architecture (Autonomous & Eternal)

```
                       ┌────────────────────────────────────────┐
                       │  GitHub Actions Cron (Mon-Fri 19:50Z) │
                       │    (1:50 PM MT / 3:50 PM ET - Close)   │
                       └───────────────────┬────────────────────┘
                                           │
                                           ▼
                       ┌────────────────────────────────────────┐
                       │   Execute: run_cloud_strategy.py       │
                       │   • Fetch ^NDX, TQQQ, SQQQ quotes       │
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
                       │  GitHub Pages Terminal (Live 24/7/365) │
                       │  https://MooMooDaBlue.github.io/       │
                       │  ndx-strategy/                         │
                       └────────────────────────────────────────┘
```

- **Daily Auto-Run**: Executes Monday–Friday at 1:50 PM Mountain Time (3:50 PM Eastern Time), 10 minutes before US market close.
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
   - **Downside Protection Floor**: When holding TQQQ, minor tests or shallow dips below the 50-day SMA do **not** trigger premature panic exits. Price must confirm a close below `SMA50 - (1.0 × ATR)` to exit to Cash.

3. **Momentum & Divergence Management**:
   - **Overbought Trim**: RSI-14 $\ge 75$ trims allocation to 30% TQQQ with momentum reset lock.
   - **Bearish Divergence**: Trims allocation to 50% TQQQ when higher price highs coincide with lower RSI highs.
   - **Tactical Shorting**: In deep bear regimes (below both SMAs), enters SQQQ only within the RSI 35–55 sweet spot, avoiding oversold short traps.

---

## 💻 Optional Local Running

You can also run everything locally on your PC whenever you wish:

```bash
# 1-Click Windows Launcher:
run_dashboard.bat

# Or via Command Line:
python web_dashboard.py
```
*(Runs the local web server at `http://localhost:5050` with an integrated background scheduler).*

---

## ⚠️ Comprehensive Legal Disclaimer — THIS IS NOT FINANCIAL ADVICE

> **READ CAREFULLY BEFORE ACCESSING, USING, OR FORKING THIS REPOSITORY:**
>
> 1. **NOT FINANCIAL, LEGAL, OR INVESTMENT ADVICE**: None of the content, code, algorithms, data, backtests, simulations, charts, trade logs, or signals presented in this repository or associated web dashboards constitute financial, investment, legal, tax, or trading advice. It is strictly not an offer, recommendation, or solicitation to buy or sell any security, ETF, derivative, or digital asset.
> 2. **EDUCATIONAL & PAPER-TRADING BENCHMARK ONLY**: This software is an open-source paper-trading framework and quantitative simulation designed purely to benchmark algorithmic models against buy-and-hold strategies. Simulated paper trades do not represent actual trading and have fundamental limitations (e.g. slippage, liquidity constraints, transaction fees, execution delays, margin/borrow rates, and psychological factors are not modeled).
> 3. **EXTREME LEVERAGED ETF RISKS**: Triple-leveraged ETFs (**TQQQ** and **SQQQ**) are high-risk financial derivatives designed solely for short-term institutional speculation. Holding leveraged ETFs over extended periods carries extreme compounding risk, volatility decay, and substantial probability of catastrophic loss or total depletion of invested capital.
> 4. **NO WARRANTY & ZERO LIABILITY**: The software is provided "as is", without warranty of any kind, express or implied. The author, maintainers, and contributors are not licensed financial advisors, broker-dealers, or registered analysts. Under no circumstances shall the author or contributors be liable for any direct, indirect, special, incidental, or consequential damages or financial losses arising from the use of or inability to use this repository. Always consult an accredited financial professional before making real investment decisions.
