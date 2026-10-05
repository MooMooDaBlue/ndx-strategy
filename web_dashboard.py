"""
Web Dashboard Server for NDX Strategy (View-Only)
=================================================
Local read-only dashboard. Does NOT schedule, does NOT execute trades, does NOT write state.
Trading is executed exclusively by GitHub Actions in the cloud.

Usage:
    python web_dashboard.py [--no-browser]
"""

import os
import sys
import json
import socket
import webbrowser
import threading
from datetime import datetime, date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import urllib.parse
import pandas as pd
import holidays

# Fix Windows console encoding for special characters
if sys.stdout.encoding != "utf-8" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
PORT = 5050

sys.path.insert(0, BASE_DIR)
import trading_strategy as ts


# ─────────────────────────────────────────────
# NYSE TRADING DAY CHECK (holidays.NYSE)
# ─────────────────────────────────────────────
def is_trading_day(dt: date | None = None) -> bool:
    """True if dt (default: today ET) is a weekday and not an NYSE market holiday."""
    if dt is None:
        dt = ts.now_et().date()
    if dt.weekday() >= 5:
        return False
    return dt not in holidays.NYSE(years=dt.year)


# ─────────────────────────────────────────────
# DATA AGGREGATION FOR DASHBOARD
# ─────────────────────────────────────────────
def _compute_stats(portfolio: dict, daily_records: list, trades: list, tqqq_price: float, sqqq_price: float) -> dict:
    starting_cap = float(portfolio.get("starting_capital", 10000.0))
    current_val = float(portfolio.get("total_value", starting_cap))
    total_pnl = current_val - starting_cap
    total_pnl_pct = (current_val / starting_cap - 1) * 100 if starting_cap > 0 else 0.0

    hwm = starting_cap
    max_dd = 0.0
    for r in daily_records:
        val = float(r.get("total_value", starting_cap))
        if val > hwm:
            hwm = val
        dd = (val - hwm) / hwm * 100 if hwm > 0 else 0.0
        if dd < max_dd:
            max_dd = dd

    latest_daily = daily_records[-1] if daily_records else {}
    ndx_price = float(latest_daily.get("ndx_price", 0.0))
    sma50 = float(latest_daily.get("sma50", 0.0))
    sma250 = float(latest_daily.get("sma250", 0.0))
    rsi = float(latest_daily.get("rsi", 50.0))

    dist_sma50_pts = ndx_price - sma50
    dist_sma50_pct = (dist_sma50_pts / sma50) * 100 if sma50 > 0 else 0
    dist_sma250_pts = ndx_price - sma250
    dist_sma250_pct = (dist_sma250_pts / sma250) * 100 if sma250 > 0 else 0

    return {
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "high_water_mark": round(hwm, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "trading_days_tracked": len(daily_records),
        "total_trades": len(trades),
        "ndx_price": round(ndx_price, 2),
        "tqqq_price": round(tqqq_price, 2),
        "sqqq_price": round(sqqq_price, 2),
        "sma50": round(sma50, 2),
        "sma250": round(sma250, 2),
        "rsi": round(rsi, 2),
        "dist_sma50_pts": round(dist_sma50_pts, 2),
        "dist_sma50_pct": round(dist_sma50_pct, 2),
        "dist_sma250_pts": round(dist_sma250_pts, 2),
        "dist_sma250_pct": round(dist_sma250_pct, 2),
    }


def get_dashboard_data() -> dict:
    """Read and compile all current data fresh from CSV and JSON state files."""
    portfolio_file = os.path.join(BASE_DIR, "portfolio_state.json")
    daily_file = os.path.join(BASE_DIR, "daily_summary.csv")
    trade_file = os.path.join(BASE_DIR, "trade_log.csv")
    log_file = os.path.join(BASE_DIR, "strategy.log")

    orig_p_file = os.path.join(BASE_DIR, "portfolio_state_original.json")
    orig_d_file = os.path.join(BASE_DIR, "daily_summary_original.csv")
    orig_t_file = os.path.join(BASE_DIR, "trade_log_original.csv")

    # 1. Primary Portfolio State (Symmetric 1.0x ATR)
    if os.path.exists(portfolio_file):
        with open(portfolio_file, "r", encoding="utf-8") as f:
            portfolio = json.load(f)
    else:
        portfolio = {
            "position": "CASH",
            "allocation_pct": 1.0,
            "cash": 10000.0,
            "tqqq_shares": 0.0,
            "sqqq_shares": 0.0,
            "tqqq_avg_cost": 0.0,
            "sqqq_avg_cost": 0.0,
            "total_value": 10000.0,
            "starting_capital": 10000.0,
            "last_signal": "System Initialized",
            "last_updated": datetime.now().isoformat(),
            "last_run_date": None,
            "trim_active": False,
            "prev_rsi": 50.0,
            "benchmark_ndx_start": 29404.63,
            "benchmark_tqqq_start": 38.71
        }

    # 2. Daily Summaries
    daily_records = []
    if os.path.exists(daily_file):
        try:
            df_daily = pd.read_csv(daily_file).fillna(0)
            daily_records = df_daily.to_dict(orient="records")
        except Exception as e:
            print(f"Error reading daily summary: {e}")

    # 3. Trade Log
    trades = []
    if os.path.exists(trade_file):
        try:
            df_trades = pd.read_csv(trade_file).fillna("")
            trades = df_trades.to_dict(orient="records")
        except Exception as e:
            print(f"Error reading trade log: {e}")

    # 4. Recent Log Lines (last 100 lines)
    recent_logs = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                recent_logs = [line.strip() for line in lines[-100:] if line.strip()]
        except Exception as e:
            print(f"Error reading log file: {e}")

    # 5. Live / Recent ETF prices from logs or portfolio
    tqqq_price = 0.0
    sqqq_price = 0.0
    for line in reversed(recent_logs):
        if "Current Prices — TQQQ:" in line:
            try:
                parts = line.split("TQQQ: $")[1].split(" | SQQQ: $")
                tqqq_price = float(parts[0])
                sqqq_price = float(parts[1].split()[0])
                break
            except Exception:
                pass
    if tqqq_price <= 0 and portfolio.get("tqqq_shares", 0) > 0:
        tqqq_price = round((portfolio["total_value"] - portfolio.get("cash", 0)) / portfolio["tqqq_shares"], 2)
    if sqqq_price <= 0:
        sqqq_price = 33.12
    if tqqq_price <= 0:
        tqqq_price = 81.01

    stats_sym = _compute_stats(portfolio, daily_records, trades, tqqq_price, sqqq_price)

    # 6. Original Agile Model
    if os.path.exists(orig_p_file):
        try:
            with open(orig_p_file, "r", encoding="utf-8") as f:
                p_orig = json.load(f)
        except Exception:
            p_orig = portfolio.copy()
    else:
        p_orig = portfolio.copy()

    orig_daily = []
    if os.path.exists(orig_d_file):
        try:
            orig_daily = pd.read_csv(orig_d_file).fillna(0).to_dict(orient="records")
        except Exception as e:
            print(f"Error reading original daily summary: {e}")

    orig_trades = []
    if os.path.exists(orig_t_file):
        try:
            orig_trades = pd.read_csv(orig_t_file).fillna("").to_dict(orient="records")
        except Exception as e:
            print(f"Error reading original trade log: {e}")

    stats_orig = _compute_stats(p_orig, orig_daily, orig_trades, tqqq_price, sqqq_price)

    starting_cap = float(portfolio.get("starting_capital", 10000.0))
    current_val = float(portfolio.get("total_value", starting_cap))
    orig_start = float(p_orig.get("starting_capital", 10000.0))
    orig_val = float(p_orig.get("total_value", orig_start))

    models = {
        "symmetric_atr": {
            "portfolio": portfolio,
            "daily_summary": daily_records,
            "trades": trades,
            "recent_logs": recent_logs,
            "stats": stats_sym,
            "starting_capital": starting_cap,
            "ending_value": round(current_val, 2),
            "total_return_pct": stats_sym["total_pnl_pct"],
        },
        "original_agile": {
            "portfolio": p_orig,
            "daily_summary": orig_daily,
            "trades": orig_trades,
            "recent_logs": recent_logs,
            "stats": stats_orig,
            "starting_capital": orig_start,
            "ending_value": round(orig_val, 2),
            "total_return_pct": stats_orig["total_pnl_pct"],
        }
    }

    server_time_str = ts.now_et().strftime("%Y-%m-%d %H:%M:%S ET")

    return {
        "portfolio": portfolio,
        "daily_summary": daily_records,
        "trades": trades,
        "recent_logs": recent_logs,
        "stats": stats_sym,
        "models": models,
        "scheduler": {
            "active": False,
            "is_active_session": is_trading_day(),
            "scheduled_time": "GitHub Actions (3:50 PM ET NYSE days)",
            "next_run_target": "Cloud-managed",
            "server_time": server_time_str,
            "last_run_date": portfolio.get("last_run_date"),
        },
        "config": {
            "starting_capital": starting_cap,
            "rsi_overbought": ts.CONFIG.get("rsi_overbought", 75),
            "rsi_trim_medium": ts.CONFIG.get("rsi_trim_medium", 50),
            "rsi_oversold": ts.CONFIG.get("rsi_oversold", 30),
            "atr_buffer_multiplier": ts.CONFIG.get("atr_buffer_multiplier", 1.0),
            "tqqq_ticker": ts.CONFIG.get("tqqq_ticker", "TQQQ"),
            "sqqq_ticker": ts.CONFIG.get("sqqq_ticker", "SQQQ"),
        }
    }


# ─────────────────────────────────────────────
# HTTP HANDLER (VIEW-ONLY)
# ─────────────────────────────────────────────
class DashboardHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler serving web assets and data API. View-only; cannot trigger trades."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/data":
            try:
                data = get_dashboard_data()
                payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        super().do_GET()

    def log_message(self, format, *args):
        # Suppress routine GET logging for static assets to keep console clean
        if len(args) > 0 and "GET /api/data" not in str(args[0]):
            return
        super().log_message(format, *args)


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def run_server(port: int = PORT, auto_open: bool = True):
    actual_port = port
    while is_port_in_use(actual_port):
        actual_port += 1

    server_address = ("127.0.0.1", actual_port)
    httpd = ThreadingHTTPServer(server_address, DashboardHandler)
    url = f"http://127.0.0.1:{actual_port}"

    print("=" * 65)
    print("  [ONLINE] NDX QUANT STRATEGY — VIEW-ONLY DASHBOARD")
    print("=" * 65)
    print(f"  Local URL:        {url}")
    print(f"  Live Data API:    {url}/api/data")
    print(f"  Execution Engine: Cloud-Only (GitHub Actions)")
    print("  Press Ctrl+C to terminate the server.")
    print("=" * 65)

    if auto_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard server stopped.")
        httpd.server_close()


if __name__ == "__main__":
    auto_browser = "--no-browser" not in sys.argv
    run_server(PORT, auto_open=auto_browser)
