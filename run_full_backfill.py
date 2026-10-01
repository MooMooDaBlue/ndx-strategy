"""
Automated Backfill and Catch-Up Runner: 2026-08-14 to 2026-10-01 (Today)
========================================================================
Runs through every missed trading day from the last execution (2026-08-13)
up to and including today (2026-10-01).

Updates:
  1. portfolio_state.json
  2. daily_summary.csv
  3. trade_log.csv
  4. strategy.log
  5. performance_chart.png
  6. Push notification (ntfy) for today's run
"""

import os
import sys
import shutil
import json
import logging
from datetime import datetime, date
import pandas as pd
import numpy as np

# Ensure root directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import trading_strategy as ts

def backup_existing_files():
    """Create timestamped backups of all existing data files before backfilling."""
    files_to_backup = [
        "portfolio_state.json",
        "daily_summary.csv",
        "trade_log.csv",
        "strategy.log",
    ]
    print("=" * 60)
    print("STEP 1: Backing up existing files...")
    for filename in files_to_backup:
        src = os.path.join(BASE_DIR, filename)
        if os.path.exists(src):
            dst = os.path.join(BASE_DIR, f"{filename}.bak_20260813")
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
                print(f"  Backed up {filename} -> {os.path.basename(dst)}")
            else:
                print(f"  Backup {os.path.basename(dst)} already exists, preserving it.")

def run_backfill():
    backup_existing_files()
    cfg = ts.CONFIG

    print("\n" + "=" * 60)
    print("STEP 2: Loading Portfolio & Fetching Market Data...")
    print("=" * 60)

    # 1. Load current portfolio state
    portfolio = ts.load_portfolio(cfg["portfolio_file"], cfg["starting_capital"])
    last_run_date = portfolio.get("last_run_date")
    print(f"  Last Run Date in portfolio: {last_run_date}")
    print(f"  Position: {portfolio['position']} | Value: ${portfolio['total_value']:,.2f}")
    print(f"  TQQQ Shares: {portfolio['tqqq_shares']:.4f} | Cash: ${portfolio['cash']:,.2f}")

    if last_run_date != "2026-08-13":
        print(f"  WARNING: Expected last_run_date to be 2026-08-13, found {last_run_date}.")

    # 2. Fetch market data for all instruments
    ndx_df = ts.fetch_data("^NDX", period="2y")
    tqqq_df = ts.fetch_data(cfg.get("tqqq_ticker", "TQQQ.TO"), period="1y")
    sqqq_df = ts.fetch_data(cfg.get("sqqq_ticker", "SQQQ.TO"), period="1y")

    # 3. Determine trading days to backfill
    today_str = "2026-10-01"
    all_dates = [d.strftime("%Y-%m-%d") for d in ndx_df.index]
    backfill_dates = [d for d in all_dates if d > last_run_date and d <= today_str]

    print(f"\nIdentified {len(backfill_dates)} trading days to process:")
    print(f"  Start: {backfill_dates[0]}  -->  End: {backfill_dates[-1]}")
    print("-" * 60)

    # Strategy log handle
    strategy_log_path = os.path.join(BASE_DIR, "strategy.log")
    
    trades_executed = []

    for idx, date_str in enumerate(backfill_dates, 1):
        is_today = (date_str == today_str)
        is_backfill = not is_today

        sub_ndx = ndx_df.loc[:date_str]
        tqqq_price = float(tqqq_df.loc[:date_str]["Close"].iloc[-1])
        sqqq_price = float(sqqq_df.loc[:date_str]["Close"].iloc[-1])

        run_time_str = f"{date_str} 13:50:15"
        run_dt = datetime.strptime(run_time_str, "%Y-%m-%d %H:%M:%S")

        # Snapshot before run for logging
        prev_pos_loaded = portfolio["position"]
        prev_val_loaded = portfolio["total_value"]

        # --- Cash Interest Accrual ---
        interest_accrued = 0.0
        days_elapsed = 0
        annual_rate = cfg.get("risk_free_annual_rate", 0.0)
        if portfolio["cash"] > 0 and portfolio.get("last_updated") and annual_rate > 0:
            try:
                last_updated_dt = datetime.fromisoformat(portfolio["last_updated"])
                days_elapsed = (run_dt - last_updated_dt).days
                if days_elapsed > 0:
                    interest_accrued = portfolio["cash"] * (annual_rate / 365) * days_elapsed
                    portfolio["cash"] += interest_accrued
                    portfolio["last_updated"] = run_dt.isoformat()
            except (ValueError, TypeError):
                pass

        # --- Signal Calculation ---
        signal_data = ts.determine_signal(
            sub_ndx, cfg,
            current_position=portfolio["position"],
            trim_active=portfolio.get("trim_active", False),
            prev_rsi=portfolio.get("prev_rsi", 50.0),
        )
        signal_data["timestamp"] = run_dt.isoformat()
        signal_data["date"] = date_str

        # Persist RSI trim state
        portfolio["trim_active"] = signal_data.get("trim_active", False)
        portfolio["prev_rsi"] = signal_data["rsi"]

        # --- Trade Execution ---
        prev_position = portfolio["position"]
        portfolio, trade = ts.execute_trade(portfolio, signal_data, tqqq_price, sqqq_price, cfg)

        # Update last run date and timestamp
        portfolio["last_run_date"] = date_str
        if not trade:
            portfolio["last_updated"] = run_dt.isoformat()

        # Save portfolio state to JSON
        ts.save_portfolio(portfolio, cfg["portfolio_file"])

        # Log trade if one occurred
        if trade:
            ts.log_trade(trade, cfg["trade_log_file"])
            trades_executed.append(trade)

        # Log daily summary
        ts.log_daily_summary(portfolio, signal_data, cfg["daily_log_file"], tqqq_price)

        # Benchmarks for logging
        ndx_start = portfolio.get("benchmark_ndx_start", signal_data["price"])
        tqqq_start = portfolio.get("benchmark_tqqq_start", tqqq_price)
        ndx_bh = (signal_data["price"] / ndx_start - 1) * 100
        tqqq_bh = (tqqq_price / tqqq_start - 1) * 100 if tqqq_price > 0 else 0.0
        pnl_pct = (portfolio["total_value"] / portfolio["starting_capital"] - 1) * 100

        # Construct log entry lines
        ms = "000" if is_backfill else f"{datetime.now().microsecond // 1000:03d}"
        ts_log = f"{date_str} 13:50:15,{ms}"

        log_lines = [
            f"{ts_log} [INFO] ============================================================",
            f"{ts_log} [INFO] NDX SMA + RSI Strategy — Daily Run",
            f"{ts_log} [INFO] Run time: {date_str} 13:50:15",
            f"{ts_log} [INFO] ============================================================",
        ]
        if is_backfill:
            log_lines.append(f"{ts_log} [INFO] [BACKFILL] This entry was retroactively generated from historical data.")
        log_lines.extend([
            f"{ts_log} [INFO] Fetching data for ^NDX...",
            f"{ts_log} [INFO]   ^NDX: {len(sub_ndx)} bars fetched, latest close: {signal_data['price']:.2f}",
            f"{ts_log} [INFO] Fetching data for TQQQ.TO...",
            f"{ts_log} [INFO]   TQQQ.TO: 5 bars fetched, latest close: {tqqq_price:.2f}",
            f"{ts_log} [INFO] Fetching data for SQQQ.TO...",
            f"{ts_log} [INFO]   SQQQ.TO: 5 bars fetched, latest close: {sqqq_price:.2f}",
            f"{ts_log} [INFO] Current Prices — TQQQ: ${tqqq_price:.2f} | SQQQ: ${sqqq_price:.2f}",
            f"{ts_log} [INFO] Portfolio loaded: {prev_pos_loaded} | Value: ${prev_val_loaded:,.2f}",
        ])
        if interest_accrued > 0:
            log_lines.append(f"{ts_log} [INFO]   Cash interest accrued: ${interest_accrued:.2f} ({days_elapsed} days @ {annual_rate*100:.1f}% annual)")

        log_lines.extend([
            f"{ts_log} [INFO] Signal: {signal_data['signal']} | RSI: {signal_data['rsi']:.1f} | NDX: {signal_data['price']:.1f} | SMA50: {signal_data['sma50']:.1f} | SMA250: {signal_data['sma250']:.1f}",
            f"{ts_log} [INFO] Reason: {signal_data['reason']}",
        ])
        if signal_data.get("in_buffer_zone"):
            log_lines.append(f"{ts_log} [INFO]   -> Re-entry buffer active: threshold = {signal_data['buffered_sma50']:.1f}")
        if signal_data.get("trim_active"):
            log_lines.append(f"{ts_log} [INFO]   -> RSI trim lock active: waiting for RSI to cross above {cfg.get('rsi_reset_threshold', 60)} from below")

        if trade:
            log_lines.append(f"{ts_log} [INFO]   TRADE SIGNAL: {prev_position} → {signal_data['signal']}")
            if trade["action"] == "SELL":
                log_lines.append(f"{ts_log} [INFO]   Sold {trade['ticker']}: {trade['shares']:.4f} shares @ ${trade['price']:.2f} = ${trade['value']:,.2f}")
                log_lines.append(f"{ts_log} [INFO]   Moved to 100% Cash: ${portfolio['cash']:,.2f}")
            elif trade["action"] == "BUY":
                log_lines.append(f"{ts_log} [INFO]   Bought {trade['ticker']} (100%): {trade['shares']:.4f} shares @ ${trade['price']:.2f} = ${trade['value']:,.2f}")
        else:
            log_lines.append(f"{ts_log} [INFO]   No change — already in {portfolio['position']}")

        log_lines.extend([
            f"{ts_log} [INFO]   Daily summary logged: Value=${portfolio['total_value']:,.2f} | P&L={pnl_pct:+.2f}%",
            f"{ts_log} [INFO]   Benchmarks: NDX B&H={ndx_bh:+.2f}% | TQQQ B&H={tqqq_bh:+.2f}%",
            f"{ts_log} [INFO] ------------------------------------------------------------",
            f"{ts_log} [INFO] PORTFOLIO SUMMARY",
            f"{ts_log} [INFO]   Position:      {portfolio['position']}",
            f"{ts_log} [INFO]   Total Value:   $   {portfolio['total_value']:>12,.2f}",
            f"{ts_log} [INFO]   Cash:          $   {portfolio['cash']:>12,.2f}",
            f"{ts_log} [INFO]   TQQQ Shares:       {portfolio['tqqq_shares']:>12.4f}",
            f"{ts_log} [INFO]   SQQQ Shares:         {portfolio['sqqq_shares']:>12.4f}",
            f"{ts_log} [INFO]   Total P&L:     $   {portfolio['total_value'] - portfolio['starting_capital']:>+12,.2f} ({pnl_pct:+.2f}%)",
            f"{ts_log} [INFO] ============================================================",
        ])

        # Push notification for today's run
        if is_today:
            made_trade = trade and trade["action"] != "CASH"
            action_info = ts._classify_action(
                signal=signal_data["signal"],
                made_trade=made_trade,
                prev_position=prev_position,
                in_buffer_zone=signal_data.get("in_buffer_zone", False),
                trim_active=signal_data.get("trim_active", False),
            )
            subject = f"{action_info['label']} | {signal_data['date']}"
            body = ts._build_notification_body(
                signal_data=signal_data,
                portfolio=portfolio,
                tqqq_price=tqqq_price,
                sqqq_price=sqqq_price,
                made_trade=made_trade,
                prev_position=prev_position,
            )
            print(f"\n  [Today] Sending live push notification via ntfy: {subject}")
            ts.send_alert(subject, body, cfg, tags=action_info["tags"], priority=action_info["priority"])
            log_lines.append(f"{ts_log} [INFO]   Push notification sent via ntfy.")

        # Append to strategy.log
        with open(strategy_log_path, "a", encoding="utf-8") as f:
            for line in log_lines:
                f.write(line + "\n")

        # Terminal progress output
        status_trade = f"** TRADE: {trade['action']} {trade['shares']:.2f} shs @ ${trade['price']:.2f} **" if trade else f"Hold {portfolio['position']}"
        print(f"[{idx:02d}/{len(backfill_dates):02d}] {date_str} | NDX: {signal_data['price']:>8.1f} | RSI: {signal_data['rsi']:>4.1f} | Val: ${portfolio['total_value']:>9,.2f} | {status_trade}")

    print("\n" + "=" * 60)
    print("STEP 3: Backfill Complete! Updating Performance Chart...")
    print("=" * 60)

    # 4. Generate updated performance chart
    try:
        import matplotlib
        matplotlib.use("Agg")  # Non-interactive backend to prevent GUI blocking
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from matplotlib.patches import Patch

        daily_df = pd.read_csv(cfg["daily_log_file"])
        dates = pd.to_datetime(daily_df["date"])

        fig, axes = plt.subplots(3, 1, figsize=(14, 10))
        fig.suptitle("NDX SMA + RSI Strategy — Paper Trading Dashboard", fontsize=14, fontweight="bold")

        start_cap = portfolio.get("starting_capital", 40000.0)

        # Chart 1: Portfolio Value
        ax1 = axes[0]
        ax1.plot(dates, daily_df["total_value"], color="#2196F3", linewidth=2, label="Portfolio Value")
        ax1.axhline(y=start_cap, color="gray", linestyle="--", alpha=0.5, label="Starting Capital")
        ax1.fill_between(dates, start_cap, daily_df["total_value"],
                         where=daily_df["total_value"] >= start_cap,
                         alpha=0.15, color="green", label="Profit")
        ax1.fill_between(dates, start_cap, daily_df["total_value"],
                         where=daily_df["total_value"] < start_cap,
                         alpha=0.15, color="red", label="Loss")
        ax1.set_title("Portfolio Value")
        ax1.set_ylabel("Value ($)")
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax1.legend(loc="upper left", fontsize=8)
        ax1.grid(True, alpha=0.3)

        # Chart 2: NDX vs SMAs
        ax2 = axes[1]
        ax2.plot(dates, daily_df["ndx_price"], color="#333", linewidth=1.5, label="NDX Price")
        ax2.plot(dates, daily_df["sma50"], color="#FF9800", linewidth=1, linestyle="--", label="SMA50")
        ax2.plot(dates, daily_df["sma250"], color="#9C27B0", linewidth=1, linestyle="--", label="SMA250")
        ax2.set_title("NDX Price vs Moving Averages")
        ax2.set_ylabel("NDX Level")
        ax2.legend(loc="upper left", fontsize=8)
        ax2.grid(True, alpha=0.3)

        # Chart 3: RSI
        ax3 = axes[2]
        ax3.plot(dates, daily_df["rsi"], color="#E91E63", linewidth=1.5, label="RSI(14)")
        ax3.axhline(y=75, color="red", linestyle="--", alpha=0.7, label="Overbought (75)")
        ax3.axhline(y=50, color="gray", linestyle="--", alpha=0.5, label="Midline (50)")
        ax3.axhline(y=30, color="green", linestyle="--", alpha=0.7, label="Oversold (30)")
        ax3.fill_between(dates, 75, daily_df["rsi"].clip(upper=100),
                         where=daily_df["rsi"] > 75, alpha=0.2, color="red")
        ax3.fill_between(dates, daily_df["rsi"].clip(lower=0), 30,
                         where=daily_df["rsi"] < 30, alpha=0.2, color="green")
        ax3.set_title("RSI(14)")
        ax3.set_ylabel("RSI")
        ax3.set_ylim(0, 100)
        ax3.legend(loc="upper left", fontsize=8)
        ax3.grid(True, alpha=0.3)

        # Position shading
        position_colors = {
            "TQQQ_100": "#4CAF50",
            "TQQQ_50": "#8BC34A",
            "TQQQ_30": "#CDDC39",
            "SQQQ": "#F44336",
            "CASH": "#9E9E9E",
        }
        for ax in axes:
            for i in range(len(daily_df) - 1):
                pos = daily_df["position"].iloc[i]
                color = position_colors.get(pos, "#9E9E9E")
                ax.axvspan(dates.iloc[i], dates.iloc[i+1], alpha=0.08, color=color)

        for ax in axes:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            ax.xaxis.set_major_locator(mdates.MonthLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

        legend_elements = [Patch(facecolor=c, alpha=0.3, label=p) for p, c in position_colors.items()]
        fig.legend(handles=legend_elements, loc="lower center", ncol=5,
                   fontsize=8, title="Position Shading", bbox_to_anchor=(0.5, 0.01))

        plt.tight_layout(rect=[0, 0.04, 1, 1])
        chart_path = os.path.join(BASE_DIR, "performance_chart.png")
        plt.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Chart generated and saved to: {chart_path}")
    except Exception as e:
        print(f"  Chart generation skipped or failed: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("FINAL PORTFOLIO STATUS (As of October 1, 2026)")
    print("=" * 60)
    final_pnl = portfolio["total_value"] - portfolio["starting_capital"]
    final_pnl_pct = (portfolio["total_value"] / portfolio["starting_capital"] - 1) * 100
    print(f"  Current Position:   {portfolio['position']}")
    print(f"  Total Portfolio:    ${portfolio['total_value']:,.2f}")
    print(f"  Cash Holdings:      ${portfolio['cash']:,.2f}")
    print(f"  TQQQ Shares:        {portfolio['tqqq_shares']:.4f} (@ ${tqqq_price:.2f})")
    print(f"  SQQQ Shares:        {portfolio['sqqq_shares']:.4f}")
    print(f"  Total P&L:          ${final_pnl:+,.2f} ({final_pnl_pct:+.2f}%)")
    print(f"  NDX Buy & Hold:     {ndx_bh:+.2f}%")
    print(f"  TQQQ Buy & Hold:    {tqqq_bh:+.2f}%")
    print(f"  Trades in Period:   {len(trades_executed)}")
    print(f"  Last Run Date:      {portfolio['last_run_date']}")
    print("=" * 60)

if __name__ == "__main__":
    run_backfill()
