"""
Cloud Runner for NDX Trading Strategy (GitHub Actions & Serverless Deployments)
=============================================================================
1. Executes daily strategy checks for both models via trading_strategy.py
2. Generates updated performance_chart.png
3. Exports aggregated dashboard data to docs/data.json (+ docs/quotes.json)

docs/ is the single frontend source: GitHub Pages serves it and the local dashboard serves it.
"""

import os
import sys
import json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")

sys.path.insert(0, BASE_DIR)
import trading_strategy as ts
import web_dashboard as wd

AGILE_FILES = dict(
    portfolio_file=os.path.join(BASE_DIR, "portfolio_state_agile.json"),
    trade_log_file=os.path.join(BASE_DIR, "trade_log_agile.csv"),
    daily_log_file=os.path.join(BASE_DIR, "daily_summary_agile.csv"),
)

# Execution window (ET): after the official close so every run uses the final daily bar.
WINDOW_START_MIN = 16 * 60
WINDOW_END_MIN = 23 * 60 + 59


def generate_chart():
    """Render high-resolution performance chart for repository preview."""
    daily_file = ts.CONFIG["daily_log_file"]
    if not os.path.exists(daily_file):
        return

    try:
        df = pd.read_csv(daily_file)
        if df.empty:
            return

        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        start_cap = ts.CONFIG["starting_capital"]

        plt.figure(figsize=(12, 6))
        plt.style.use("dark_background")
        plt.plot(df.index, df["total_value"], label="Symmetric ATR — Total Value ($)", color="#00E676", linewidth=2.2)
        if "total_value_agile" in df:
            plt.plot(df.index, df["total_value_agile"], label="Original Agile — Total Value ($)",
                     color="#29B6F6", linewidth=1.4, alpha=0.8)
        plt.axhline(start_cap, color="#78909C", linestyle="--", alpha=0.7,
                    label=f"Starting Capital (${start_cap:,.0f})")
        if "source" in df and (df["source"] == "live").any():
            plt.axvline(df.index[(df["source"] == "live").argmax()], color="#FFD54F", linestyle=":",
                        label="Backtest → live paper trading")
        plt.yscale("log")
        plt.title("NDX SMA + RSI Strategy — Equity Curve (backtest + live paper, log scale)",
                  fontsize=14, fontweight="bold", pad=15)
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
    if data.get("ndx_heatmap", {}).get("quotes"):
        quotes_target = os.path.join(DOCS_DIR, "quotes.json")
        with open(quotes_target, "w", encoding="utf-8") as f:
            json.dump(data["ndx_heatmap"], f, separators=(",", ":"))
        print(f"  [DATA] Exported lightweight quotes: {quotes_target}")


def in_execution_window() -> bool:
    """16:00-23:59 ET (same session day). GitHub cron is often hours late, so the window must be
    wide; _already_ran_today() keeps it to one run per day. FORCE_RUN=true bypasses."""
    if os.environ.get("FORCE_RUN", "").lower() in ("1", "true", "yes"):
        return True
    t = ts.now_et()
    minutes = t.hour * 60 + t.minute
    return WINDOW_START_MIN <= minutes <= WINDOW_END_MIN


def _already_ran_today() -> bool:
    today = ts.now_et().date().isoformat()
    for f in (ts.CONFIG["portfolio_file"], AGILE_FILES["portfolio_file"]):
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                if json.load(fh).get("last_run_date") != today:
                    return False
        else:
            return False
    return True


def _agile_daily_fields() -> dict:
    """Agile model's value/position for today's row in the primary daily summary."""
    with open(AGILE_FILES["portfolio_file"], encoding="utf-8") as f:
        p = json.load(f)
    return {"total_value_agile": round(p["total_value"], 2), "pos_agile": p["position"]}


def main():
    ts.trim_log_file()
    ts.setup_logging()
    print("=" * 65)
    print(f"  NDX STRATEGY — CLOUD RUN — {ts.now_et():%Y-%m-%d %H:%M:%S} ET")
    print("=" * 65)
    if not ts.is_trading_day():
        print("  Not an NYSE trading day — nothing to do.")
        return
    if not in_execution_window():
        print(f"  Outside 16:00-23:59 ET window (now {ts.now_et():%H:%M} ET) — skipping.")
        return
    if _already_ran_today():
        print("  Both models already ran today — skipping.")
        return

    market_data = ts.fetch_market_data()
    # Agile first, so the primary model's daily row records today's Agile value
    ran_agile = ts.run_strategy(model="original_agile", market_data=market_data,
                                notify=False, **AGILE_FILES)
    ran_main = ts.run_strategy(model="symmetric_atr", market_data=market_data, notify=True,
                               extra_daily_fields=_agile_daily_fields())
    if ran_agile or ran_main:
        generate_chart()
        export_pages_data()
    print("  Cloud run complete.")


if __name__ == "__main__":
    main()
