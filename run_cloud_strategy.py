"""
Cloud Runner for NDX Trading Strategy (GitHub Actions & Serverless Deployments)
=============================================================================
1. Executes daily strategy checks for both models via trading_strategy.py
2. Generates updated performance_chart.png
3. Exports aggregated dashboard data to docs/data.json
4. Syncs web frontend assets into docs/ for GitHub Pages static hosting
"""

import os
import sys
import json
import shutil
import pandas as pd
from datetime import datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
WEB_DIR = os.path.join(BASE_DIR, "web")

os.makedirs(DOCS_DIR, exist_ok=True)

sys.path.insert(0, BASE_DIR)
import trading_strategy as ts
import web_dashboard as wd

ORIG_FILES = dict(
    portfolio_file=os.path.join(BASE_DIR, "portfolio_state_original.json"),
    trade_log_file=os.path.join(BASE_DIR, "trade_log_original.csv"),
    daily_log_file=os.path.join(BASE_DIR, "daily_summary_original.csv"),
)


def generate_chart():
    """Render high-resolution performance chart for repository preview."""
    daily_file = os.path.join(BASE_DIR, "daily_summary.csv")
    if not os.path.exists(daily_file):
        return

    try:
        df = pd.read_csv(daily_file)
        if df.empty:
            return

        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)

        plt.figure(figsize=(12, 6))
        plt.style.use("dark_background")
        plt.plot(df.index, df["total_value"], label="Portfolio Total Value ($)", color="#00E676", linewidth=2.2)
        plt.axhline(10000, color="#78909C", linestyle="--", alpha=0.7, label="Starting Capital ($10,000)")
        plt.title("NDX SMA + RSI Strategy — Protected Equity Curve", fontsize=14, fontweight="bold", pad=15)
        plt.xlabel("Date", fontsize=11)
        plt.ylabel("Portfolio Value ($ USD)", fontsize=11)
        plt.grid(True, linestyle=":", alpha=0.4)
        plt.legend(loc="upper left", framealpha=0.3)
        plt.tight_layout()

        chart_path = os.path.join(BASE_DIR, "performance_chart.png")
        plt.savefig(chart_path, dpi=150)
        plt.close()
        print("  [CHART] performance_chart.png re-rendered successfully.")
    except Exception as e:
        print(f"  [CHART ERROR] {e}")


def export_pages_data():
    """Export the dashboard payload to docs/ for GitHub Pages (compact, no volatile fields)."""
    data = wd.get_dashboard_data()
    data.get("scheduler", {}).pop("server_time", None)
    target = os.path.join(DOCS_DIR, "data.json")
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"  [DATA] Exported static payload: {target}")

    # Also export lightweight quotes.json for fast polling
    if "ndx_heatmap" in data and data["ndx_heatmap"]:
        quotes_target = os.path.join(DOCS_DIR, "quotes.json")
        with open(quotes_target, "w", encoding="utf-8") as f:
            json.dump(data["ndx_heatmap"], f, separators=(",", ":"))
        print(f"  [DATA] Exported lightweight quotes: {quotes_target}")

    for asset in ["index.html", "style.css", "app.js"]:
        src = os.path.join(WEB_DIR, asset)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(DOCS_DIR, asset))
            print(f"  [ASSET] Synced {asset} -> docs/")


def in_execution_window() -> bool:
    """15:45-17:30 ET. Works year-round regardless of DST; FORCE_RUN=true bypasses."""
    if os.environ.get("FORCE_RUN", "").lower() in ("1", "true", "yes"):
        return True
    t = ts.now_et()
    minutes = t.hour * 60 + t.minute
    return 15 * 60 + 45 <= minutes <= 17 * 60 + 30


def _already_ran_today() -> bool:
    today = ts.now_et().date().isoformat()
    for f in (ts.CONFIG["portfolio_file"], ORIG_FILES["portfolio_file"]):
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                if json.load(fh).get("last_run_date") != today:
                    return False
    return True


def main():
    print("=" * 65)
    print(f"  NDX STRATEGY — CLOUD RUN — {ts.now_et():%Y-%m-%d %H:%M:%S} ET")
    print("=" * 65)
    if not wd.is_trading_day():
        print("  Not an NYSE trading day — nothing to do.")
        return
    if not in_execution_window():
        print(f"  Outside 15:45-17:30 ET window (now {ts.now_et():%H:%M} ET) — skipping.")
        return
    if _already_ran_today():
        print("  Both models already ran today — skipping.")
        return

    market_data = ts.fetch_market_data()
    # Original first, so the primary model's daily row reads today's Original value (fixes C6)
    ran_orig = ts.run_strategy(model="original_agile", market_data=market_data,
                               notify=False, **ORIG_FILES)
    ran_main = ts.run_strategy(model="symmetric_atr", market_data=market_data, notify=True)
    if ran_orig or ran_main:
        generate_chart()
        export_pages_data()
    print("  Cloud run complete.")


if __name__ == "__main__":
    main()
