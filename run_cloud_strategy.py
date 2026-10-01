"""
Cloud Runner for NDX Trading Strategy (GitHub Actions & Serverless Deployments)
=============================================================================
1. Executes daily strategy check via trading_strategy.py
2. Generates updated performance_chart.png
3. Exports aggregated dashboard data to docs/data.json and web/data.json
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
os.makedirs(WEB_DIR, exist_ok=True)

sys.path.insert(0, BASE_DIR)
import trading_strategy as ts
import web_dashboard as wd


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
    """Compile and export latest data payload for GitHub Pages static hosting."""
    data = wd.get_dashboard_data()

    # Save to both web/data.json and docs/data.json
    for out_dir in [WEB_DIR, DOCS_DIR]:
        target = os.path.join(out_dir, "data.json")
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"  [DATA] Exported static payload: {target}")

    # Copy frontend assets to docs/ for GitHub Pages
    for asset in ["index.html", "style.css", "app.js"]:
        src = os.path.join(WEB_DIR, asset)
        dst = os.path.join(DOCS_DIR, asset)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  [ASSET] Synced {asset} -> docs/")


def main():
    print("=" * 65)
    print("  NDX STRATEGY — CLOUD EXECUTION & GITHUB PAGES EXPORT")
    print(f"  Execution Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 65)

    # 1. Check if trading day
    if not wd.is_trading_day():
        print("  Notice: Today is not an active NYSE trading day (weekend/holiday).")
        print("  Refreshing dashboard export without executing new trades.")
    else:
        print("  Active NYSE trading day detected. Executing strategy...")
        ts.run_strategy()

    # 2. Re-render chart
    generate_chart()

    # 3. Export static data for GitHub Pages
    export_pages_data()

    print("\n  Cloud execution and Pages sync complete!")
    print("=" * 65)


if __name__ == "__main__":
    main()
