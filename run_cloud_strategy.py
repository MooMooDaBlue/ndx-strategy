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


def sync_original_strategy():
    """Evaluate and update the Original Agile strategy model for the current trading day."""
    orig_p_file = os.path.join(BASE_DIR, "portfolio_state_original.json")
    orig_d_file = os.path.join(BASE_DIR, "daily_summary_original.csv")
    orig_t_file = os.path.join(BASE_DIR, "trade_log_original.csv")
    if not os.path.exists(orig_p_file):
        return

    today_str = datetime.now().date().isoformat()
    try:
        with open(orig_p_file, "r", encoding="utf-8") as f:
            p_orig = json.load(f)
        if p_orig.get("last_run_date") == today_str:
            print("  [ORIGINAL MODEL] Already up to date for today.")
            return

        ndx_df = ts.fetch_data("^NDX", period="2y")
        tqqq_df = ts.fetch_data("TQQQ", period="5d")
        sqqq_df = ts.fetch_data("SQQQ", period="5d")
        tqqq_price = float(tqqq_df["Close"].iloc[-1])
        sqqq_price = float(sqqq_df["Close"].iloc[-1])

        s50 = float(ndx_df["Close"].rolling(50).mean().iloc[-1])
        s250 = float(ndx_df["Close"].rolling(250).mean().iloc[-1])
        price = float(ndx_df["Close"].iloc[-1])

        delta = ndx_df["Close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        rsi = float((100 - (100 / (1 + rs))).iloc[-1])

        last_dt_str = p_orig.get("last_updated", f"{today_str}T00:00:00")
        try:
            last_dt = datetime.fromisoformat(last_dt_str)
            days = (datetime.now() - last_dt).days
        except Exception:
            days = 0
        cash = float(p_orig.get("cash", 0.0))
        if cash > 0 and days > 0:
            cash += cash * (0.045 / 365) * days

        pos = p_orig.get("position", "CASH")
        t_shares = float(p_orig.get("tqqq_shares", 0.0))
        s_shares = float(p_orig.get("sqqq_shares", 0.0))
        trim_active = p_orig.get("trim_active", False)
        prev_rsi = float(p_orig.get("prev_rsi", 50.0))

        if trim_active and (prev_rsi < 60) and (rsi >= 60):
            trim_active = False

        reentry_thresh = s50 * 1.01
        in_buf_entry = (not pos.startswith("TQQQ")) and (price >= s50) and (price <= reentry_thresh)

        above_250 = price >= s250
        above_50 = price >= s50
        below_50 = price < s50
        below_250 = price < s250

        signal = "CASH"
        reason = ""
        if above_250:
            if below_50:
                signal = "CASH"
                trim_active = False
                reason = f"Clean exit: NDX {price:.1f} broke below SMA50 ({s50:.1f})"
            elif above_50:
                if in_buf_entry:
                    signal = "CASH"
                    reason = f"1% confirmation buffer: NDX {price:.1f} <= threshold ({reentry_thresh:.1f})"
                elif rsi >= 75:
                    signal = "TQQQ_30"
                    trim_active = True
                    reason = f"Overbought: RSI {rsi:.1f} >= 75"
                elif trim_active:
                    signal = "TQQQ_30"
                    reason = "Overbought trim active"
                else:
                    signal = "TQQQ_100"
                    reason = f"Bull trend confirmed: Price > SMA50 & SMA250, RSI {rsi:.1f}"
        elif below_250 and below_50:
            trim_active = False
            if 35 <= rsi <= 55:
                signal = "SQQQ"
                reason = f"Bear signal: Below SMAs, RSI {rsi:.1f} in SQQQ zone"
            else:
                signal = "CASH"
                reason = "Defensive cash in bear regime"
        elif below_250 and above_50:
            if in_buf_entry:
                signal = "CASH"
                reason = "1% confirmation buffer below SMA250"
            elif rsi >= 50:
                signal = "TQQQ_30"
                reason = "Counter-trend rally below SMA250"
            else:
                signal = "CASH"
                reason = "Below SMA250, insufficient momentum"

        curr_val = cash + t_shares * tqqq_price + s_shares * sqqq_price

        if signal != pos:
            cash = curr_val
            t_shares = 0.0
            s_shares = 0.0
            alloc_pct = 1.0
            if signal == "TQQQ_100":
                t_shares = cash / tqqq_price
                cash = 0.0
                alloc_pct = 1.0
            elif signal == "TQQQ_50":
                t_shares = (cash * 0.5) / tqqq_price
                cash = cash * 0.5
                alloc_pct = 0.5
            elif signal == "TQQQ_30":
                t_shares = (cash * 0.3) / tqqq_price
                cash = cash * 0.7
                alloc_pct = 0.3
            elif signal == "SQQQ":
                s_shares = cash / sqqq_price
                cash = 0.0
                alloc_pct = 1.0
            else:
                alloc_pct = 0.0

            p_orig["position"] = signal
            p_orig["allocation_pct"] = alloc_pct
            p_orig["cash"] = round(cash, 2)
            p_orig["tqqq_shares"] = round(t_shares, 4)
            p_orig["sqqq_shares"] = round(s_shares, 4)
            p_orig["tqqq_avg_cost"] = tqqq_price if t_shares > 0 else 0.0
            p_orig["sqqq_avg_cost"] = sqqq_price if s_shares > 0 else 0.0

            trade_rec = {
                "date": today_str,
                "timestamp": datetime.now().isoformat(),
                "action": "BUY" if "TQQQ" in signal or signal == "SQQQ" else "SELL",
                "ticker": "TQQQ" if "TQQQ" in signal else ("SQQQ" if signal == "SQQQ" else "CASH"),
                "shares": round(t_shares or s_shares, 4),
                "price": tqqq_price if "TQQQ" in signal else (sqqq_price if signal == "SQQQ" else 0.0),
                "value": round(curr_val, 2),
                "ndx_price": round(price, 2),
                "sma50": round(s50, 2),
                "sma250": round(s250, 2),
                "rsi": round(rsi, 2),
                "reason": reason
            }
            pd.DataFrame([trade_rec]).to_csv(orig_t_file, mode="a", header=not os.path.exists(orig_t_file), index=False)

        curr_val = cash + t_shares * tqqq_price + s_shares * sqqq_price
        p_orig["total_value"] = round(curr_val, 2)
        p_orig["last_updated"] = datetime.now().isoformat()
        p_orig["last_run_date"] = today_str
        p_orig["last_signal"] = reason
        p_orig["trim_active"] = trim_active
        p_orig["prev_rsi"] = rsi

        with open(orig_p_file, "w", encoding="utf-8") as f:
            json.dump(p_orig, f, indent=2)

        start_cap = float(p_orig.get("starting_capital", 10000.0))
        ndx_start = float(p_orig.get("benchmark_ndx_start", price))
        tqqq_start = float(p_orig.get("benchmark_tqqq_start", tqqq_price))
        rec_orig = {
            "date": today_str,
            "position": p_orig["position"],
            "allocation_pct": p_orig.get("allocation_pct", 1.0),
            "total_value": round(curr_val, 2),
            "cash": round(p_orig["cash"], 2),
            "tqqq_shares": round(p_orig["tqqq_shares"], 4),
            "sqqq_shares": round(p_orig["sqqq_shares"], 4),
            "ndx_price": round(price, 2),
            "sma50": round(s50, 2),
            "sma250": round(s250, 2),
            "rsi": round(rsi, 2),
            "signal": p_orig["position"],
            "reason": reason,
            "pnl_dollar": round(curr_val - start_cap, 2),
            "pnl_pct": round((curr_val / start_cap - 1) * 100, 2),
            "ndx_buyhold_pnl_pct": round((price / ndx_start - 1) * 100, 2),
            "tqqq_buyhold_pnl_pct": round((tqqq_price / tqqq_start - 1) * 100, 2)
        }
        pd.DataFrame([rec_orig]).to_csv(orig_d_file, mode="a", header=not os.path.exists(orig_d_file), index=False)
        print("  [ORIGINAL MODEL] Synced Original Agile model successfully.")
    except Exception as e:
        print(f"  [ORIGINAL MODEL ERROR] {e}")


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
        print("  Active NYSE trading day detected. Executing primary strategy...")
        ts.run_strategy()
        print("  Executing dual-model Original Agile sync...")
        sync_original_strategy()

    # 2. Re-render chart
    generate_chart()

    # 3. Export static data for GitHub Pages
    export_pages_data()

    print("\n  Cloud execution and Pages sync complete!")
    print("=" * 65)


if __name__ == "__main__":
    main()

