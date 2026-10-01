# NDX Quant Systematic Trading Strategy & Terminal

[![Daily Strategy Execution & Pages Sync](https://github.com/MooMooDaBlue/ndx-strategy/actions/workflows/daily_strategy.yml/badge.svg)](https://github.com/MooMooDaBlue/ndx-strategy/actions/workflows/daily_strategy.yml)
[![Live Web Dashboard](https://img.shields.io/badge/Live_Dashboard-GitHub_Pages-00E676?style=flat&logo=googlechrome&logoColor=white)](https://MooMooDaBlue.github.io/ndx-strategy/)

An institutional-grade, fully automated algorithmic paper-trading strategy and real-time monitoring terminal for NASDAQ-100 leveraged ETFs (**TQQQ / SQQQ**). 

Runs **100% serverless and autonomously** in the cloud via GitHub Actions and GitHub Pages with zero required local hardware or maintenance.

---

## 🌐 Live Cloud Dashboard

The live interactive terminal is hosted continuously on GitHub Pages:

👉 **[https://MooMooDaBlue.github.io/ndx-strategy/](https://MooMooDaBlue.github.io/ndx-strategy/)**

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

## 📌 Disclaimer

This project is an open-source educational paper-trading simulator and quantitative benchmark created for research and demonstration purposes. It does not constitute financial or investment advice. Always conduct your own research before trading leveraged financial instruments.
