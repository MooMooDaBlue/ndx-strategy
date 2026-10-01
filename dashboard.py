"""
Portfolio Dashboard — NDX Strategy
=====================================
Run this anytime to see your current portfolio status,
performance chart, and trade history.

Run with: python dashboard.py
"""

import pandas as pd
import json
import os
import sys
from datetime import datetime

# Fix Windows console encoding for emoji characters
if sys.stdout.encoding != "utf-8" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Try to import matplotlib for charting ──
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    CHART_AVAILABLE = True
except ImportError:
    CHART_AVAILABLE = False

CONFIG = {
    "portfolio_file": "portfolio_state.json",
    "trade_log_file": "trade_log.csv",
    "daily_log_file": "daily_summary.csv",
    "starting_capital": 40_000.00,
}


def load_portfolio():
    if not os.path.exists(CONFIG["portfolio_file"]):
        print("  No portfolio found. Run trading_strategy.py first.")
        return None
    with open(CONFIG["portfolio_file"]) as f:
        return json.load(f)


def load_daily_log():
    if not os.path.exists(CONFIG["daily_log_file"]):
        return None
    df = pd.read_csv(CONFIG["daily_log_file"], parse_dates=["date"])
    return df


def load_trade_log():
    if not os.path.exists(CONFIG["trade_log_file"]):
        return None
    df = pd.read_csv(CONFIG["trade_log_file"], parse_dates=["date"])
    return df


def print_portfolio_summary(portfolio):
    pnl = portfolio["total_value"] - portfolio["starting_capital"]
    pnl_pct = (portfolio["total_value"] / portfolio["starting_capital"] - 1) * 100

    print("\n" + "=" * 55)
    print("  📊 NDX STRATEGY — PORTFOLIO DASHBOARD")
    print("=" * 55)
    print(f"  Last Updated:    {(portfolio.get('last_updated') or 'N/A')[:19]}")
    print(f"  Current Position: {portfolio['position']}")
    print("-" * 55)
    print(f"  Starting Capital: ${portfolio['starting_capital']:>12,.2f}")
    print(f"  Current Value:    ${portfolio['total_value']:>12,.2f}")
    print(f"  Cash:             ${portfolio['cash']:>12,.2f}")
    print(f"  TQQQ Shares:      {portfolio['tqqq_shares']:>12.4f}")
    print(f"  SQQQ Shares:      {portfolio['sqqq_shares']:>12.4f}")
    print("-" * 55)
    print(f"  Total P&L:        ${pnl:>+12,.2f}")
    print(f"  Total Return:     {pnl_pct:>+11.2f}%")
    print("=" * 55)

    last_signal = portfolio.get("last_signal", "N/A")
    print(f"\n  Last Signal: {last_signal}")


def print_trade_history(trade_log):
    if trade_log is None or trade_log.empty:
        print("\n  No trades recorded yet.")
        return

    print(f"\n{'='*55}")
    print(f"  📋 TRADE HISTORY ({len(trade_log)} trades)")
    print(f"{'='*55}")
    print(f"  {'Date':<12} {'Action':<8} {'Ticker':<10} {'Shares':>10} {'Price':>10} {'Value':>12}")
    print(f"  {'-'*11} {'-'*7} {'-'*9} {'-'*10} {'-'*10} {'-'*12}")

    for _, row in trade_log.tail(20).iterrows():
        date_str = str(row["date"])[:10] if pd.notna(row["date"]) else "N/A"
        print(f"  {date_str:<12} {str(row['action']):<8} {str(row['ticker']):<10} "
              f"{row['shares']:>10.4f} {row['price']:>10.2f} ${row['value']:>11,.2f}")

    if len(trade_log) > 20:
        print(f"\n  (Showing last 20 of {len(trade_log)} trades. See trade_log.csv for full history.)")


def print_performance_stats(daily_log):
    if daily_log is None or daily_log.empty:
        print("\n  No daily history yet.")
        return

    total_days = len(daily_log)
    start_val = CONFIG["starting_capital"]
    end_val = daily_log["total_value"].iloc[-1]
    total_return = (end_val / start_val - 1) * 100

    # Best/worst days
    daily_log["daily_return"] = daily_log["total_value"].pct_change() * 100
    best_day = daily_log.loc[daily_log["daily_return"].idxmax()] if len(daily_log) > 1 else None
    worst_day = daily_log.loc[daily_log["daily_return"].idxmin()] if len(daily_log) > 1 else None

    # Days in each position
    position_counts = daily_log["position"].value_counts()

    print(f"\n{'='*55}")
    print(f"  📈 PERFORMANCE STATISTICS")
    print(f"{'='*55}")
    print(f"  Trading Days Tracked: {total_days}")
    print(f"  Total Return:         {total_return:+.2f}%")
    print(f"\n  Days by Position:")
    for pos, count in position_counts.items():
        pct = count / total_days * 100
        print(f"    {pos:<15} {count:>4} days ({pct:.1f}%)")

    if best_day is not None:
        print(f"\n  Best Day:   {str(best_day['date'])[:10]}  {best_day['daily_return']:+.2f}%")
    if worst_day is not None:
        print(f"  Worst Day:  {str(worst_day['date'])[:10]}  {worst_day['daily_return']:+.2f}%")
    print("=" * 55)


def plot_performance(daily_log):
    if not CHART_AVAILABLE:
        print("\n  ℹ️  Install matplotlib to see charts: pip install matplotlib")
        return
    if daily_log is None or len(daily_log) < 2:
        print("\n  Not enough data to chart yet (need at least 2 days).")
        return

    fig, axes = plt.subplots(3, 1, figsize=(14, 10))
    fig.suptitle("NDX SMA + RSI Strategy — Paper Trading Dashboard", fontsize=14, fontweight="bold")

    dates = pd.to_datetime(daily_log["date"])

    # ── Chart 1: Portfolio Value ──────────────
    ax1 = axes[0]
    ax1.plot(dates, daily_log["total_value"], color="#2196F3", linewidth=2, label="Portfolio Value")
    ax1.axhline(y=CONFIG["starting_capital"], color="gray", linestyle="--", alpha=0.5, label="Starting Capital")
    ax1.fill_between(dates, CONFIG["starting_capital"], daily_log["total_value"],
                     where=daily_log["total_value"] >= CONFIG["starting_capital"],
                     alpha=0.15, color="green", label="Profit")
    ax1.fill_between(dates, CONFIG["starting_capital"], daily_log["total_value"],
                     where=daily_log["total_value"] < CONFIG["starting_capital"],
                     alpha=0.15, color="red", label="Loss")
    ax1.set_title("Portfolio Value")
    ax1.set_ylabel("Value ($)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.3)

    # ── Chart 2: NDX vs SMAs ─────────────────
    ax2 = axes[1]
    ax2.plot(dates, daily_log["ndx_price"], color="#333", linewidth=1.5, label="NDX Price")
    ax2.plot(dates, daily_log["sma50"], color="#FF9800", linewidth=1, linestyle="--", label="SMA50")
    ax2.plot(dates, daily_log["sma250"], color="#9C27B0", linewidth=1, linestyle="--", label="SMA250")
    ax2.set_title("NDX Price vs Moving Averages")
    ax2.set_ylabel("NDX Level")
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(True, alpha=0.3)

    # ── Chart 3: RSI ─────────────────────────
    ax3 = axes[2]
    ax3.plot(dates, daily_log["rsi"], color="#E91E63", linewidth=1.5, label="RSI(14)")
    ax3.axhline(y=75, color="red", linestyle="--", alpha=0.7, label="Overbought (75)")
    ax3.axhline(y=50, color="gray", linestyle="--", alpha=0.5, label="Midline (50)")
    ax3.axhline(y=30, color="green", linestyle="--", alpha=0.7, label="Oversold (30)")
    ax3.fill_between(dates, 75, daily_log["rsi"].clip(upper=100),
                     where=daily_log["rsi"] > 75, alpha=0.2, color="red")
    ax3.fill_between(dates, daily_log["rsi"].clip(lower=0), 30,
                     where=daily_log["rsi"] < 30, alpha=0.2, color="green")
    ax3.set_title("RSI(14)")
    ax3.set_ylabel("RSI")
    ax3.set_ylim(0, 100)
    ax3.legend(loc="upper left", fontsize=8)
    ax3.grid(True, alpha=0.3)

    # ── Shade positions ───────────────────────
    position_colors = {
        "TQQQ_100": "#4CAF50",
        "TQQQ_50": "#8BC34A",
        "TQQQ_30": "#CDDC39",
        "SQQQ": "#F44336",
        "CASH": "#9E9E9E",
    }
    for ax in axes:
        for i in range(len(daily_log) - 1):
            pos = daily_log["position"].iloc[i]
            color = position_colors.get(pos, "#9E9E9E")
            ax.axvspan(dates.iloc[i], dates.iloc[i+1], alpha=0.08, color=color)

    # Format x-axis dates
    for ax in axes:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    # Legend for position shading
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=c, alpha=0.3, label=p) for p, c in position_colors.items()]
    fig.legend(handles=legend_elements, loc="lower center", ncol=5,
               fontsize=8, title="Position Shading", bbox_to_anchor=(0.5, 0.01))

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    chart_path = "performance_chart.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    print(f"\n  📊 Chart saved to: {chart_path}")
    plt.show()


def main():
    portfolio = load_portfolio()
    if portfolio is None:
        return

    daily_log = load_daily_log()
    trade_log = load_trade_log()

    print_portfolio_summary(portfolio)
    print_performance_stats(daily_log)
    print_trade_history(trade_log)
    plot_performance(daily_log)

    print(f"\n  Files in this directory:")
    for f in ["portfolio_state.json", "trade_log.csv", "daily_summary.csv", "strategy.log", "performance_chart.png"]:
        exists = "✅" if os.path.exists(f) else "⬜"
        print(f"    {exists} {f}")


if __name__ == "__main__":
    main()
